import os
import re
import json  
import utils 
import concurrent.futures 

# ==========================================
# 상수 및 정규식 정의 (공통 사용)
# ==========================================
JAPANESE_REGEX_WIDE = re.compile(r'[\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\uff00-\uffef\u4e00-\u9faf\u3400-\u4dbf]')
BRACKET_REGEX = re.compile(r'(「[^」]+」|『[^』]+』)')
CHUNK_REGEX = re.compile(r'[^\x00-\x1f]+')

# [추가] 정제 규칙 (Cleaning Rules)
# 패턴에 매칭되면, 해당 그룹(괄호 안의 내용)만 추출해서 사용합니다.
# (정규식 패턴, 추출할 그룹 번호)
CLEANING_RULES = [
    # CASE 1: UABEA 덤프 포맷 (1 string m_Text = "텍스트") -> "텍스트"만 추출
    # 정규식 설명: m_Text = " 뒤에 오는 내용 중 " 앞까지를 캡처
    (re.compile(r'm_Text\s*=\s*"(.*?)"'), 1),
    
    # CASE 2: 스크립트 화자 태그 (#speaker=소녀=) -> "소녀"만 추출
    # 정규식 설명: #speaker= 뒤에 오는 내용을 캡처 (뒤에 오는 =는 제거 로직에서 처리)
    (re.compile(r'#speaker=(.*)'), 1),
]
# [추가] 유효 문자 확인용 정규식 (필터링 강화)
# 알파벳(a-z), 한글, 일본어(히라/가타/한자) 중 '최소 하나'는 있어야 유효한 텍스트로 인정
# 즉, 숫자(0-9)나 특수문자(▶, =, <=)만 있는 경우를 거르기 위함입니다.
VALID_CHAR_REGEX = re.compile(r'[a-zA-Z\u3040-\u30ff\u4e00-\u9faf\u3400-\u4dbf\uac00-\ud7a3]')

# ==========================================
# 내부 헬퍼 함수
# ==========================================
def _get_glossary_map(masking_data):
    """
    리스트 형태의 masking_data를 받아 검색용 패턴과 매핑 정보를 반환
    """
    if not masking_data:
        return None, None
        
    # 긴 단어부터 매칭되도록 정렬 (utils에서 이미 정렬되지만 안전장치)
    sorted_data = sorted(masking_data, key=lambda x: len(x['src']), reverse=True)
    
    if not sorted_data:
        return None, None

    # 정규식 패턴 생성
    pattern = re.compile('|'.join(re.escape(item['src']) for item in sorted_data))
    return pattern, sorted_data

    # [추가] 청크 정제 함수
def clean_extracted_chunk(text):
    """
    추출된 텍스트 덩어리가 특정 포맷(UABEA 등)일 경우, 
    핵심 텍스트만 발라내어 반환합니다.
    """
    for pattern, group_idx in CLEANING_RULES:
        match = pattern.search(text)
        if match:
            # 매칭된 그룹(알맹이)만 추출
            extracted = match.group(group_idx).strip()
            
            # (옵션) 끝에 붙은 불필요한 '=' 제거 (예: #speaker=소녀= -> 소녀)
            if extracted.endswith('='):
                extracted = extracted.rstrip('=')
                
            return extracted
    
    # 매칭되는 규칙이 없으면 원본 그대로 반환
    return text

# ==========================================
# [Worker] 개별 파일 추출 작업
# ==========================================
def _worker_extract(args):
    path, options, masking_data, glossary_pattern = args
    found_lines = []
    try:
        try:
            with open(path, 'r', encoding='utf-8') as f: text = f.read()
        except UnicodeDecodeError:
            enc = utils.detect_encoding(path)
            with open(path, 'r', encoding=enc, errors='replace') as f: text = f.read()

        clean = re.sub(r'[\x00-\x09\x0b\x0c\x0e-\x1f\x7f]', '', text)

        # 1. 괄호 문자 우선 처리
        if options.get('group_brackets'):
            for b in BRACKET_REGEX.findall(clean):
                processed_b = b
                
                # 정제 로직
                processed_b = clean_extracted_chunk(processed_b)

                # 마스킹 적용
                if options.get('extract_masking') and glossary_pattern:
                    def mask_cb(m):
                        word = m.group(0)
                        for idx, item in enumerate(masking_data):
                            if item['src'] == word:
                                return f"__MASK_{idx:03d}__"
                        return word
                    processed_b = glossary_pattern.sub(mask_cb, processed_b)
                
                if processed_b:
                    found_lines.append(processed_b)
                
                clean = clean.replace(b, "") 

        # 2. 일반 텍스트 청크 처리
        for m in CHUNK_REGEX.finditer(clean):
            chunk = m.group().strip()
            
            # [정제 수행]
            cleaned_chunk = clean_extracted_chunk(chunk)
            
            if not cleaned_chunk:
                continue

            # [신뢰도 판단] 정제 과정에서 껍데기가 벗겨졌다면 -> 의도된 텍스트 (신뢰도 높음)
            is_high_confidence = (cleaned_chunk != chunk)

            # [핵심 수정] 검증을 위한 임시 텍스트 생성
            # \n, \r 같은 이스케이프 문자는 '문자'가 아니라 '서식'으로 취급하여 제거하고 판단합니다.
            # 이렇게 하면 "002\n"에서 "\n"이 사라져 "002"만 남게 되므로, 문자(n)가 있다고 착각하지 않습니다.
            validation_text = cleaned_chunk.replace(r'\n', '').replace(r'\r', '')

            has_japanese = JAPANESE_REGEX_WIDE.search(validation_text)
            has_valid_char = VALID_CHAR_REGEX.search(validation_text)

            # [저장 조건]
            # 1. 신뢰도가 높은 경우 (m_Text 등)
            #    -> 이스케이프(\n)를 뺀 나머지 부분에 유효 문자(알파벳/한글/한자)가 있어야 함
            if is_high_confidence:
                if has_valid_char:
                    found_lines.append(cleaned_chunk)
            
            # 2. 일반 텍스트인 경우
            #    -> 일본어 포함 & 2글자 이상 (검증 텍스트 기준)
            elif has_japanese and len(validation_text) > 1:
                found_lines.append(cleaned_chunk)
                
        return path, found_lines, None

    except Exception as e:
        return path, [], str(e)

# ==========================================
# 1. 텍스트 추출 로직 (Process Extract)
# ==========================================
def process_extract(src_dir, out_path_or_dir, options, log_callback, progress_callback=None):
    if not src_dir or not out_path_or_dir:
        log_callback("!! 경로를 지정해주세요.")
        return

    log_callback("=== 추출 작업 시작 (멀티스레딩/스마트 정제) ===")
    
    masking_data = utils.load_glossary_data(options.get('glossary_path'))
    glossary_pattern = None
    
    if options.get('extract_masking') and masking_data:
        glossary_pattern, _ = _get_glossary_map(masking_data)
        log_callback(f">> 용어집 마스킹 활성화: {len(masking_data)}개 항목")

    extracted_lines = []
    extracted_set = set()
    
    files = [f for f in os.listdir(src_dir) if f.lower().endswith(('.txt', '.json', '.dat'))]
    total_files = len(files)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for fname in files:
            path = os.path.join(src_dir, fname)
            args = (path, options, masking_data, glossary_pattern)
            futures.append(executor.submit(_worker_extract, args))

        for idx, future in enumerate(concurrent.futures.as_completed(futures)):
            path, lines, error = future.result()
            fname = os.path.basename(path)

            if error:
                log_callback(f"!! {fname} 읽기 실패: {error}")
            else:
                for line in lines:
                    if line not in extracted_set:
                        extracted_set.add(line)
                        extracted_lines.append(line)

            if (idx + 1) % 100 == 0:
                log_callback(f">> [분석] ({idx + 1}/{total_files}) 완료")
            
            if progress_callback and total_files > 0:
                progress_callback((idx + 1) / total_files, fname)

    save_path = out_path_or_dir
    if os.path.isdir(save_path):
        save_path = os.path.join(save_path, "_EXTRACTED_DB.txt")

    try:
        with open(save_path, 'w', encoding='utf-8') as f:
            for line in extracted_lines:
                f.write(f"{line}=\n")
        log_callback(f"=== 완료: {len(extracted_lines)}줄 추출됨 ===")
        log_callback(f"저장 위치: {save_path}")
    except Exception as e:
        log_callback(f"!! 저장 실패: {e}")


# ==========================================
# [Helper] JSON 재귀 치환 함수
# ==========================================
def _recursive_json_replace(data, pattern, repl_func, change_counter):
    if isinstance(data, dict):
        return {k: _recursive_json_replace(v, pattern, repl_func, change_counter) for k, v in data.items()}
    elif isinstance(data, list):
        return [_recursive_json_replace(item, pattern, repl_func, change_counter) for item in data]
    elif isinstance(data, str):
        new_val, count = pattern.subn(repl_func, data)
        if count > 0:
            change_counter[0] += count
        return new_val
    else:
        return data

# ==========================================
# [Worker] 개별 파일 번역 작업
# ==========================================
def _worker_translate(args):
    path, out_dir, db, options, pattern = args
    fname = os.path.basename(path)
    
    # 1. 포맷 모드 및 옵션 설정
    fmt_option = options.get('db_format', '자동감지 (Auto)')
    
    mode_custom = "사용자지정" in fmt_option
    mode_json = "JSON" in fmt_option
    mode_txt = "TXT" in fmt_option
    mode_auto = "자동감지" in fmt_option
    
    is_json_ext = fname.lower().endswith('.json')
    if mode_auto:
        if is_json_ext: mode_json = True
        else: mode_txt = True
            
    nl_key = options.get('newline_key', '\\n')
    sp_key = options.get('space_key', ' ')
    
    master_smart = options.get('smart_mode', True)
    use_header = master_smart and options.get('smart_header', True)
    use_json_fix = master_smart and options.get('smart_json', True)
    use_special = master_smart and options.get('smart_special', True)
    
    is_smart_save = options.get('smart_save', True)
    
    try:
        # 파일 읽기
        with open(path, 'rb') as f:
            raw_bytes = f.read()
        
        try:
            text = raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            enc = utils.detect_encoding(path)
            text = raw_bytes.decode(enc, errors='replace')

        changed_count = 0
        final_text = text

        # ---------------------------------------------------------
        # [내부 함수] 치환 로직
        # ---------------------------------------------------------
        def replace_cb(m, for_json_parser=False):
            original_val = db[m.group(0)]
            val = original_val
            
            if mode_custom:
                target_nl = options.get('newline_val', '\n')
                target_sp = options.get('space_val', ' ')
                real_nl = '\n' if target_nl == "[Enter]" else target_nl
                real_sp = '\u00A0' if target_sp == "[NBSP]" else target_sp
                val = val.replace(nl_key, real_nl).replace(sp_key, real_sp)
            else:
                if use_special:
                    val = val.replace(nl_key, '\n').replace(sp_key, '\u00A0')
                else:
                    val = val.replace(nl_key, '\n')

                if mode_json and use_json_fix and not for_json_parser:
                    val = val.replace('\n', '\\n').replace('"', '\\"')
                    val = val.replace('\u00A0', ' ')
            return val

        # ---------------------------------------------------------
        # [내부 함수] 혼합 문장 감지 (Mixed Language Check)
        # ---------------------------------------------------------
        def is_mixed_text(t):
            has_kr = bool(utils.KOREAN_REGEX.search(t))
            has_jp = bool(utils.JAPANESE_REGEX_WIDE.search(t))
            return has_kr and has_jp

        # =========================================================
        # [처리 로직]
        # =========================================================
        processed_as_json = False
        
        # --- CASE 1: JSON 모드 ---
        if mode_json:
            try:
                json_data = json.loads(text)
                change_counter = [0]
                
                def recursive_wrapper(data):
                    if isinstance(data, str):
                        new_val, cnt = pattern.subn(lambda m: replace_cb(m, for_json_parser=True), data)
                        if cnt > 0:
                            # [JSON 검증] 혼합 시 해당 값만 원문 롤백
                            if is_mixed_text(new_val):
                                return data 
                            change_counter[0] += cnt
                            return new_val
                        return data
                    elif isinstance(data, dict):
                        return {k: recursive_wrapper(v) for k, v in data.items()}
                    elif isinstance(data, list):
                        return [recursive_wrapper(item) for item in data]
                    else:
                        return data

                new_json_data = recursive_wrapper(json_data)
                changed_count = change_counter[0]
                final_text = json.dumps(new_json_data, ensure_ascii=False, indent=4)
                processed_as_json = True
            except json.JSONDecodeError:
                pass 
        
        # --- CASE 2: TXT 모드 (하이브리드 방식) ---
        if not processed_as_json:
            # 1단계: 전체 텍스트 대상 글로벌 치환 (멀티라인 매칭 지원을 위해)
            # 여기서는 카운트를 세지 않고 일단 변환합니다.
            temp_text, raw_change_count = pattern.subn(lambda m: replace_cb(m, for_json_parser=False), text)
            
            if raw_change_count > 0:
                # 2단계: 줄 단위 검증 및 롤백
                # 원문과 변환문의 줄 수가 같을 때만 안전하게 검증 가능
                orig_lines = text.splitlines(keepends=True)
                new_lines = temp_text.splitlines(keepends=True)
                
                if len(orig_lines) == len(new_lines):
                    final_lines = []
                    valid_changes = 0
                    
                    for o_line, n_line in zip(orig_lines, new_lines):
                        # 변환이 일어난 줄만 검사
                        if o_line != n_line:
                            if is_mixed_text(n_line):
                                # 실패: 혼합 문장이면 원문 사용
                                final_lines.append(o_line)
                            else:
                                # 성공: 번역문 사용
                                final_lines.append(n_line)
                                valid_changes += 1
                        else:
                            final_lines.append(n_line)
                    
                    final_text = "".join(final_lines)
                    changed_count = valid_changes
                else:
                    # 줄 수가 달라졌다면(매우 드문 케이스) 검증을 포기하고 변환본 전체 적용
                    # (멀티라인 치환 등으로 개행 문자가 달라질 수 있음)
                    final_text = temp_text
                    changed_count = raw_change_count
            else:
                final_text = text
                changed_count = 0

        # [저장 로직]
        if is_smart_save and changed_count == 0:
            return fname, 0, False, None 

        if not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True) 

        out_bytes = final_text.encode('utf-8')
        
        # [헤더 보호]
        if use_header and not processed_as_json and len(raw_bytes) >= 4 and len(out_bytes) >= 4:
            if raw_bytes[0] == 0 or raw_bytes[1] == 0: 
                temp_arr = bytearray(out_bytes)
                temp_arr[:4] = raw_bytes[:4]
                out_bytes = bytes(temp_arr)

        with open(os.path.join(out_dir, fname), 'wb') as f:
            f.write(out_bytes)
            
        return fname, changed_count, True, None 

    except Exception as e:
        return fname, 0, False, str(e)

# ==========================================
# 2. 번역 적용 로직 (Process Translate)
# ==========================================
def process_translate(src_dir, out_dir, db_path, options, log_callback, progress_callback=None):
    if not (src_dir and out_dir and db_path):
        log_callback("!! 경로를 모두 지정해주세요.")
        return

    log_callback("=== 번역 적용 시작 (멀티스레딩) ===")

    db = {}
    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' not in line: continue
                k, v = line.strip().split('=', 1)
                db[k.strip()] = v.strip()
        
        keys = sorted(db.keys(), key=len, reverse=True)
        if not keys:
            log_callback("!! DB 파일이 비어있습니다.")
            return
        
        pattern = re.compile('|'.join(re.escape(k) for k in keys))
        log_callback(f">> DB 로드 완료: {len(db)}개 항목")
        
    except Exception as e:
        log_callback(f"!! DB 로드 실패: {e}")
        return

    files = [f for f in os.listdir(src_dir) if f.lower().endswith(('.txt', '.json', '.dat'))]
    total_files = len(files)
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for fname in files:
            path = os.path.join(src_dir, fname)
            args = (path, out_dir, db, options, pattern)
            futures.append(executor.submit(_worker_translate, args))
        
        for idx, future in enumerate(concurrent.futures.as_completed(futures)):
            fname, count, saved, error = future.result()
            
            if error:
                log_callback(f"!! {fname} 처리 실패: {error}")
            elif saved:
                is_json = fname.lower().endswith('.json')
                log_callback(f"[{'JSON' if is_json else 'TXT'}] {fname} 처리됨 ({count}개)")

            if progress_callback and total_files > 0:
                progress_callback((idx + 1) / total_files, fname)

    log_callback("=== 모든 번역 작업 완료 ===")

# ==========================================
# 3. DB 마스킹 유틸리티 (Process DB Masking)
# ==========================================
def process_db_masking(db_path, glossary_path, mode, log_callback):
    """
    마스킹 적용 및 해제 (좌변/우변 분리 로직 적용)
    :param mode: 'apply' (원문 -> 마스킹ID), 'restore' (마스킹ID -> 원문/번역문)
    """
    if not (db_path and glossary_path):
        log_callback("!! DB 파일과 용어집 경로를 모두 지정해주세요.")
        return

    # 용어집 로드
    masking_data = utils.load_glossary_data(glossary_path)
    if not masking_data:
        log_callback("!! 용어집을 불러올 수 없거나 비어 있습니다.")
        return

    log_callback(f"=== DB 마스킹 {'적용' if mode == 'apply' else '해제(복원)'} 시작 ===")
    
    try:
        # 1. 검색 및 치환을 위한 매핑 테이블 생성
        # Apply용: 긴 단어부터 매칭되도록 정렬된 패턴
        glossary_pattern, sorted_data = _get_glossary_map(masking_data)
        
        # Restore용: Mask ID를 Key로 하는 고속 조회 딕셔너리
        id_to_src = {item['mask_id']: item['src'] for item in masking_data}
        id_to_tgt = {item['mask_id']: item['tgt'] for item in masking_data}
        
        # 마스킹 ID 패턴 (예: __MSK_0000__)
        restore_pattern = re.compile(r"__MSK_\d{4}__")

        updated_lines = []
        
        # -------------------------------------------------------
        # [내부 함수] 마스킹 적용 (Apply)
        # -------------------------------------------------------
        def _apply_text(text):
            if not glossary_pattern: return text
            # 텍스트 내의 원문을 찾아 Mask ID로 치환
            def _cb(m):
                word = m.group(0)
                for item in sorted_data:
                    if item['src'] == word:
                        return item['mask_id']
                return word
            return glossary_pattern.sub(_cb, text)

        # -------------------------------------------------------
        # [내부 함수] 마스킹 해제 (Restore)
        # -------------------------------------------------------
        def _restore_text(text, target_map):
            # 텍스트 내의 Mask ID를 찾아 target_map(Src 또는 Tgt)으로 치환
            def _cb(m):
                mask_id = m.group(0)
                return target_map.get(mask_id, mask_id) # 맵에 없으면 그대로 유지
            return restore_pattern.sub(_cb, text)

        # 파일 처리 시작
        with open(db_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        count = 0
        for line in lines:
            line = line.strip()
            if not line:
                updated_lines.append("\n")
                continue
            
            # 주석 처리
            if line.startswith('//'):
                updated_lines.append(f"{line}\n")
                continue

            # 등호(=) 기준 분리
            left = line
            right = ""
            has_equal = '=' in line
            
            if has_equal:
                parts = line.split('=', 1)
                left = parts[0]
                right = parts[1]

            # [모드별 로직 수행]
            if mode == 'apply':
                # 적용: 좌변/우변 모두 동일한 Mask ID로 변환
                new_left = _apply_text(left)
                new_right = _apply_text(right) if has_equal else ""
                
            else: # mode == 'restore'
                # 해제: 좌변은 원문(Src), 우변은 번역문(Tgt)으로 변환
                new_left = _restore_text(left, id_to_src)
                
                if has_equal:
                    new_right = _restore_text(right, id_to_tgt)
                else:
                    # 등호가 없는 문장(순수 텍스트 파일 등)은 번역문으로 치환하는 것이 자연스러움
                    new_left = _restore_text(left, id_to_tgt)
                    new_right = ""

            # 결과 재조립
            if has_equal:
                updated_lines.append(f"{new_left}={new_right}\n")
            else:
                updated_lines.append(f"{new_left}\n")
                
            count += 1

        # 결과 저장
        suffix = "_MASKED.txt" if mode == "apply" else "_RESTORED.txt"
        out_path = os.path.splitext(db_path)[0] + suffix
    
        with open(out_path, 'w', encoding='utf-8') as f:
            f.writelines(updated_lines)
        
        log_callback(f">> 처리 완료 ({count} 라인)")
        log_callback(f">> 저장 경로: {out_path}")
    
    except Exception as e:
        log_callback(f"!! 작업 중 오류 발생: {e}")