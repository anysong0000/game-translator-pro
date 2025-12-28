# utils.py
import chardet
import os
import re

# ==========================================
# [상수] 정규식 패턴
# ==========================================
JAPANESE_REGEX_WIDE = re.compile(r'[\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\uff00-\uffef\u4e00-\u9faf\u3400-\u4dbf]')
BRACKET_REGEX = re.compile(r'(「[^」]+」|『[^』]+』)')
KOREAN_REGEX = re.compile(r'[\uac00-\ud7a3]')

# ==========================================
# [함수] 파일 및 데이터 처리
# ==========================================
def detect_encoding(file_path):
    """파일의 인코딩을 감지하여 반환 (기본값: utf-8)"""
    try:
        with open(file_path, 'rb') as f:
            raw = f.read(4096)
            result = chardet.detect(raw)
            return result['encoding'] or 'utf-8'
    except:
        return 'utf-8'

def load_glossary_data(path):
    """
    용어집 파일을 읽어서 리스트 구조로 반환합니다.
    
    [변경된 지원 형식]
    1. CSV 형식 (3단): 원문, 의미/힌트, 번역문
       예: ビクン, 몸이 튀는 모양, 움찔
    2. 등호 형식 (기존): 원문=번역문
       
    [반환 값]
    [
        {'src': '원문', 'tgt': '번역문', 'hint': '힌트', 'mask_id': '__MSK_000__'},
        ...
    ]
    """
    glossary_list = []
    
    if not path or not os.path.exists(path):
        return glossary_list
    
    try:
        enc = detect_encoding(path)
        with open(path, 'r', encoding=enc, errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('//'): continue

                src, tgt, hint = "", "", ""

                # 1. 쉼표(,)가 포함된 CSV 형식 (원문, 힌트, 번역)
                if ',' in line:
                    parts = line.split(',', 2) 
                    src = parts[0].strip()
                    # [변경] 2번째가 힌트, 3번째가 번역문
                    if len(parts) >= 2: hint = parts[1].strip()
                    if len(parts) >= 3: tgt = parts[2].strip()
                
                # 2. 등호(=)가 포함된 기존 형식 (원문=번역)
                elif '=' in line:
                    parts = line.split('=', 1)
                    src = parts[0].strip()
                    if len(parts) >= 2: tgt = parts[1].strip()
                
                if src and tgt:
                    glossary_list.append({'src': src, 'tgt': tgt, 'hint': hint})

        # [중요] 긴 단어 우선 매칭을 위해 길이 내림차순 정렬
        glossary_list.sort(key=lambda x: len(x['src']), reverse=True)
        
        # [신규] 마스킹 ID 부여 (정렬된 순서대로 고유 ID 할당)
        # 이 ID는 적용/해제 시 동일하게 사용됨
        for i, item in enumerate(glossary_list):
            item['mask_id'] = f"__MSK_{i:04d}__"
            
        return glossary_list

    except Exception as e:
        print(f"!! [utils.py] 용어집 로드 중 오류: {e}")
        return []