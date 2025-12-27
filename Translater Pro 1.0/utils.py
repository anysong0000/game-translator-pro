# utils.py
import chardet
import os
import re

# ==========================================
# [상수] 정규식 패턴 (다른 모듈에서 공통 사용)
# ==========================================
# 일본어(한자, 히라가나, 가타카나) 및 전각 문자 범위
JAPANESE_REGEX_WIDE = re.compile(r'[\u3000-\u303f\u3040-\u309f\u30a0-\u30ff\uff00-\uffef\u4e00-\u9faf\u3400-\u4dbf]')
# 괄호 패턴 (「...」, 『...』)
BRACKET_REGEX = re.compile(r'(「[^」]+」|『[^』]+』)')

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
    용어집 파일을 읽어서 표준화된 리스트 구조로 반환합니다.
    
    [지원 형식]
    1. CSV 형식 (권장): 원문, 번역문, 힌트
       예: ズボズボ, [#B11], 깊은 소리
    2. 등호 형식 (기존): 원문=번역문
       예: New Game=새 게임
       
    [반환 값]
    [
        {'src': '원문', 'tgt': '번역문', 'hint': '힌트(없으면 빈문자열)'},
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
                # 빈 줄이나 주석(//) 건너뛰기
                if not line or line.startswith('//'): continue

                src, tgt, hint = "", "", ""

                # 1. 쉼표(,)가 포함된 CSV 형식 처리
                # 예: Word, Trans, Hint
                if ',' in line:
                    parts = line.split(',', 2) # 최대 3개 조각으로 분리
                    src = parts[0].strip()
                    if len(parts) >= 2: tgt = parts[1].strip()
                    if len(parts) >= 3: hint = parts[2].strip()
                
                # 2. 등호(=)가 포함된 기존 형식 처리
                # 예: Word=Trans
                elif '=' in line:
                    parts = line.split('=', 1)
                    src = parts[0].strip()
                    if len(parts) >= 2: tgt = parts[1].strip()
                    # 등호 방식은 힌트 없음
                
                # 유효한 데이터(원문과 번역문이 모두 있음)만 추가
                if src and tgt:
                    glossary_list.append({'src': src, 'tgt': tgt, 'hint': hint})

        # [중요] 긴 단어 우선 매칭을 위해 길이 내림차순 정렬
        # (예: 'Fire'보다 'Fireball'이 먼저 처리되어야 함)
        glossary_list.sort(key=lambda x: len(x['src']), reverse=True)
        
        return glossary_list

    except Exception as e:
        print(f"!! [utils.py] 용어집 로드 중 오류: {e}")
        return []