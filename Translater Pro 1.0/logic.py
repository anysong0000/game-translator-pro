import os
import re
import json  
import utils 
import concurrent.futures 
import time

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
# [Helper] 리스트를 청크로 나누는 함수
# ==========================================
def chunk_list(lst, n):
    """리스트를 n개씩 자릅니다."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# ==========================================
# [Worker] 파일 묶음(Batch) 처리 작업
# ==========================================
def _worker_translate_batch(args):
    file_list, src_dir, out_dir, db, options, pattern = args
    
    processed_cnt = 0
    saved_cnt = 0
    last_error = None
    
    nl_key = options.get('newline_key', '\\n')
    sp_key = options.get('space_key', ' ')
    is_smart_save = options.get('smart_save', True)
    
    if not pattern or not db:
        return 0, 0, "DB Empty"

    for i, fname in enumerate(file_list):
        # [핵심] 10개 처리할 때마다 0.001초 쉼 -> UI 스레드에 제어권 양보 (응답없음 방지)
        if i % 10 == 0:
            time.sleep(0.001)

        path = os.path.join(src_dir, fname)
        is_json_ext = fname.lower().endswith('.json')
        processed_cnt += 1
        
        try:
            with open(path, 'rb') as f:
                raw_bytes = f.read()
            
            try:
                text = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                enc = utils.detect_encoding(path)
                text = raw_bytes.decode(enc, errors='replace')

            # 치환 로직 (구버전 방식)
            def replace_cb(m):
                match_str = m.group(0)
                temp_key = match_str.replace(r'\r\n', '\n').replace(r'\r', '\n').replace(r'\n', '\n')
                temp_key = temp_key.replace('\r\n', '\n').replace('\r', '\n')
                parts = [p.strip() for p in temp_key.split('\n')]
                search_key = "\n".join(parts)

                if search_key not in db: return match_str 
                val = db[search_key]

                if is_json_ext:
                    val = val.replace(nl_key, '\\n').replace('"', '\\"').replace(sp_key, ' ')
                else:
                    val = val.replace(nl_key, '\n').replace(sp_key, '\u00A0')
                return val

            final_text, changed_count = pattern.subn(replace_cb, text)

            if is_smart_save and changed_count == 0:
                continue 

            if not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True) 

            # ▼▼▼ [수정] 파일 확장자에 따라 인코딩 차별화 ▼▼▼
            if is_json_ext:
                # JSON 파일: BOM 없이 순수 UTF-8로 저장 (UABEA 호환성)
                out_bytes = final_text.encode('utf-8')
            else:
                # TXT/DAT 파일: 한글 인식을 위해 BOM(서명) 추가
                out_bytes = final_text.encode('utf-8-sig')
            # ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲

            # [헤더 보호 로직] (JSON은 텍스트라 헤더 보호가 필요 없으므로 안전함)
            if len(raw_bytes) >= 4 and len(out_bytes) >= 4:
                # 단, 원본이 JSON이 아닌 바이너리 파일일 경우에만 작동하도록 조건 추가 권장
                # (is_json_ext가 False일 때만)
                if not is_json_ext and (raw_bytes[0] == 0 or raw_bytes[1] == 0): 
                    temp_arr = bytearray(out_bytes)
                    temp_arr[:4] = raw_bytes[:4]
                    out_bytes = bytes(temp_arr)

            with open(os.path.join(out_dir, fname), 'wb') as f:
                f.write(out_bytes)
            saved_cnt += 1

        except Exception as e:
            last_error = f"{fname}: {str(e)}"
    
    return processed_cnt, saved_cnt, last_error

# ==========================================
# 2. 번역 적용 로직 (Process Translate)
# ==========================================
def process_translate(src_dir, out_dir, db_path, options, log_callback, progress_callback=None):
    if not (src_dir and out_dir and db_path):
        log_callback("!! 경로를 모두 지정해주세요.")
        return

    log_callback("=== 번역 적용 시작 (반응형 배치 모드) ===")

    # 1. DB 로드 (기존과 동일)
    db = {}
    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            for line in f:
                if '=' not in line: continue
                k, v = line.strip().split('=', 1)
                clean_k = k.strip().replace(r'\r\n', '\n').replace(r'\r', '\n').replace(r'\n', '\n')
                clean_k = clean_k.replace('\r\n', '\n').replace('\r', '\n')
                db[clean_k] = v.strip()
        
        keys = sorted(db.keys(), key=len, reverse=True)
        if not keys:
            log_callback("!! DB 파일이 비어있습니다.")
            return

        escaped_keys = []
        flexible_newline = r'[ \t]*(?:\\r\\n|\\n|\\r|\r\n|\n|\r)[ \t]*'
        ascii_check = re.compile(r'^[\x00-\x7F]+$')

        # ▼▼▼ [추가] 옵션값 가져오기 ▼▼▼
        use_safe_mode = options.get('safe_english', False)

        for k in keys:
            parts = k.split('\n')
            safe_parts = [re.escape(p) for p in parts]
            pattern_str = flexible_newline.join(safe_parts)
            # ▼▼▼ [수정] 옵션이 켜져 있을 때만 "비싼 연산" 수행 ▼▼▼
            if use_safe_mode and len(parts) == 1 and ascii_check.match(k):
                # 안전 장치 (따옴표/괄호 보호 + JSON 키 보호) - 연산 비용 높음
                safe_prefix = r'(?<=[\"\'\>])'
                safe_suffix = r'(?=[\"\'\<])'
                json_guard  = r'(?!\s*:)'
                pattern_str = safe_prefix + pattern_str + safe_suffix + json_guard
            
            escaped_keys.append(pattern_str)
        
        pattern = re.compile('|'.join(escaped_keys))
        log_callback(f">> DB 로드 완료: {len(db)}개 항목 (영문보호: {'ON' if use_safe_mode else 'OFF'})")
        
    except Exception as e:
        log_callback(f"!! DB 로드 실패: {e}")
        return

    # 2. 파일 목록 스캔
    files = [f for f in os.listdir(src_dir) if f.lower().endswith(('.txt', '.json', '.dat'))]
    total_files = len(files)
    
    # ---------------------------------------------------------------
    # [최적화 1] 배치 크기를 줄여서 로그 갱신 속도를 높임 (5분 대기 해소)
    # ---------------------------------------------------------------
    BATCH_SIZE = 50 
    file_chunks = list(utils.chunk_list(files, BATCH_SIZE)) if hasattr(utils, 'chunk_list') else list(chunk_list(files, BATCH_SIZE))
    
    # ---------------------------------------------------------------
    # [최적화 2] CPU 코어 여유 확보
    # ---------------------------------------------------------------
    cpu_count = os.cpu_count() or 4
    safe_workers = max(1, cpu_count - 1) 
    
    log_callback(f">> 총 {total_files}개 파일 번역 시작...")

    total_scanned = 0
    total_saved = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=safe_workers) as executor:
        futures = []
        for chunk in file_chunks:
            args = (chunk, src_dir, out_dir, db, options, pattern)
            futures.append(executor.submit(_worker_translate_batch, args))
        
        for idx, future in enumerate(concurrent.futures.as_completed(futures)):
            p_cnt, s_cnt, error = future.result()
            total_scanned += p_cnt
            total_saved += s_cnt
            
            if error: log_callback(f"!! 오류: {error}")
            
            # 진행률 업데이트
            if progress_callback:
                progress = total_scanned / total_files if total_files > 0 else 0
                progress_callback(progress, f"{total_scanned}/{total_files} 완료 ({int(progress*100)}%)")
                
            # [최적화 3] 로그는 배치 5번마다 한 번씩만 출력 (너무 빠르면 읽기 힘듦)
            if idx % 5 == 0 or idx == len(file_chunks) - 1:
                 log_callback(f">> 진행 중: {total_scanned}개 완료 (생성: {total_saved}개)")


    # [수정] 최종 결과 로그를 명확하게 분리
    log_callback("========================================")
    log_callback(f"   [작업 완료]")
    log_callback(f"   - 전체 스캔 파일: {total_scanned}개")
    log_callback(f"   - 실제 생성 파일: {total_saved}개 (스마트 저장)")
    log_callback("========================================")

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
