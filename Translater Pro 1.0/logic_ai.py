import os
import time
import re
import json
import math
import requests
import tiktoken
import tempfile
from datetime import datetime, timedelta
from openai import OpenAI
import anthropic
import deepl
from google import genai
from google.genai import types

import utils

# ==========================================
# [설정] 기본 UI 표시용 모델 목록
# ==========================================
PROVIDER_MODELS = {
    "OPENAI": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    "ANTHROPIC": ["claude-3-5-sonnet-20240620", "claude-3-haiku-20240307"],
    "GOOGLE": ["gemini-2.5-pro", "gemini-2.5-flash"],
    "DEEPL": ["DeepL API (Character based)"]
}

class PricingEngine:
    LITELLM_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
    CACHE_FILENAME = "pricing_cache.json"
    CACHE_DURATION = timedelta(days=1)

    def __init__(self):
        self.price_map = {}
        self.cache_path = self._determine_cache_path()
        self.load_data()

    def _determine_cache_path(self):
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            candidate = os.path.join(base_dir, self.CACHE_FILENAME)
            if not os.path.exists(candidate):
                with open(candidate, 'w', encoding='utf-8') as f:
                    f.write("{}")
            return candidate
        except:
            return os.path.join(tempfile.gettempdir(), self.CACHE_FILENAME)

    def load_data(self):
        if self._is_cache_valid():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    self.price_map = json.load(f)
                self._update_global_models() 
                return
            except: pass
        self.fetch_community_data()

    def _is_cache_valid(self):
        if not os.path.exists(self.cache_path): return False
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(self.cache_path))
            return datetime.now() - mtime < self.CACHE_DURATION
        except: return False

    def fetch_community_data(self):
        try:
            response = requests.get(self.LITELLM_URL, timeout=10)
            response.raise_for_status()
            self.price_map = response.json()
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.price_map, f, ensure_ascii=False, indent=2)
            self._update_global_models()
        except Exception as e:
            print(f"[PricingEngine] Update failed: {e}")

    def _update_global_models(self):
        global PROVIDER_MODELS
        try:
            clean_openai = set()
            clean_google = set()
            clean_anthropic = set()

            BAD_KEYWORDS = [
                "search", "realtime", "tts", "audio", "thinking", "embed", 
                "moderation", "vision", "bison", "gecko", "dall-e", 
                "instruct", "tuning", "video", "image", "online", 
                "32k", "16k", "preview" 
            ]

            CORE_KEYWORDS = {
                "google": ["gemini-1.5", "gemini-2.0", "gemini-2.5"], 
                "openai": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo", "o1-mini", "o1-preview"], 
                "anthropic": ["claude-3-5-sonnet", "claude-3-opus", "claude-3-haiku"]
            }

            for key in self.price_map.keys():
                name = key.lower()
                if '/' in key: continue  
                if any(bad in name for bad in BAD_KEYWORDS): continue 

                if re.search(r'-(us|eu)$', name): continue
                if re.search(r'-(us|eu)-', name): continue
                if re.search(r'-(us|eu)\d', name): continue
                if re.search(r'^(us|eu)', name): continue

                if 'gemini' in name:
                    if any(core in name for core in CORE_KEYWORDS['google']):
                        if re.search(r'-\d{3}$', name): continue 
                        clean_google.add(key)
                elif 'gpt' in name or 'o1' in name:
                    if not any(core in name for core in CORE_KEYWORDS['openai']): continue
                    if re.search(r'-\d{4}', name): continue 
                    clean_openai.add(key)
                elif 'claude' in name:
                    if any(core in name for core in CORE_KEYWORDS['anthropic']):
                        if '2023' in name: continue 
                        clean_anthropic.add(key)

            if clean_google: PROVIDER_MODELS["GOOGLE"] = sorted(list(clean_google), reverse=True)
            if clean_openai: PROVIDER_MODELS["OPENAI"] = sorted(list(clean_openai), key=len)
            if clean_anthropic: PROVIDER_MODELS["ANTHROPIC"] = sorted(list(clean_anthropic), reverse=True)
            print(f"[System] Clean List: OpenAI({len(clean_openai)}), Google({len(clean_google)}), Anthropic({len(clean_anthropic)})")
        except Exception as e:
            print(f"[PricingEngine] Update failed: {e}")

    def get_price(self, model_name):
        if model_name in self.price_map:
            info = self.price_map[model_name]
            return info.get("input_cost_per_token", 0) * 1_000_000, info.get("output_cost_per_token", 0) * 1_000_000
        return 0.0, 0.0

pricing_engine = PricingEngine()

class BaseProvider:
    def __init__(self, options):
        self.options = options
        self.temperature = options.get('temperature', 0.1)

    def translate(self, system_prompt, user_text, retry_count=3):
        for attempt in range(retry_count):
            try:
                return self._call_api(system_prompt, user_text)
            except Exception as e:
                if attempt == retry_count - 1:
                    raise e
                time.sleep(2 ** attempt) 
        return ""
    def _call_api(self, system_prompt, user_text): raise NotImplementedError

class OpenAIProvider(BaseProvider):
    def __init__(self, api_key, model, options):
        super().__init__(options)
        self.client = OpenAI(api_key=api_key)
        self.model = model
        
    def _call_api(self, system_prompt, user_text):
        # JSON 모드 사용 여부 확인
        response_format = {"type": "json_object"} if self.options.get('force_json') else None
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_text}],
            temperature=self.temperature,
            response_format=response_format
        )
        return response.choices[0].message.content.strip()

class AnthropicProvider(BaseProvider):
    def __init__(self, api_key, model, options):
        super().__init__(options)
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
    def _call_api(self, system_prompt, user_text):
        # Claude는 response_format 파라미터가 다름 (현재는 프롬프트 의존성이 높음)
        response = self.client.messages.create(
            model=self.model, max_tokens=4096, system=system_prompt,
            messages=[{"role": "user", "content": user_text}], 
            temperature=self.temperature
        )
        return response.content[0].text.strip()

class GoogleGeminiProvider(BaseProvider):
    def __init__(self, api_key, model, options):
        super().__init__(options)
        self.client = genai.Client(api_key=api_key)
        self.model_name = model
        
        self.safety_settings = [
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
        ]

    def _call_api(self, system_prompt, user_text):
        full_prompt = f"{system_prompt}\n\n[INPUT DATA]\n{user_text}"
        
        # [변경] force_json 옵션에 따라 MIME Type 결정
        mime_type = "application/json" if self.options.get('force_json') else "text/plain"
        
        max_retries = 10
        base_wait_time = 60

        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        safety_settings=self.safety_settings,
                        temperature=self.temperature,
                        response_mime_type=mime_type
                    )
                )

                if response.text:
                    return response.text.strip()
                else:
                    print(f"!! [경고] Gemini 응답 공백 (필터됨). 원문 유지.")
                    return "{}" 
            
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    wait_time = base_wait_time + (attempt * 10)
                    print(f"\n[Gemini] 429 한도 초과. {wait_time}초 대기... ({attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                
                if "NoneType" in error_str:
                    return "{}"

                print(f"!! [오류] Gemini API 호출 중 문제: {e}")
                if attempt == max_retries - 1:
                    return "{}"
                time.sleep(2)

        return "{}"

class DeepLProvider(BaseProvider):
    def __init__(self, api_key):
        self.translator = deepl.Translator(api_key)
    def _call_api(self, system_prompt, user_text):
        result = self.translator.translate_text(user_text, target_lang="KO", preserve_formatting=True)
        return result.text

def calculate_estimates(target_path, provider, model, log_callback):
    if not target_path or not os.path.exists(target_path):
        log_callback("!! 대상 경로가 올바르지 않습니다.")
        return None
        
    pricing_engine.load_data()
    
    total_chars = 0
    total_tokens = 0
    file_count = 0
    total_lines = 0
    
    enc = None
    if provider == "OPENAI":
        try: enc = tiktoken.encoding_for_model(model)
        except: enc = tiktoken.get_encoding("cl100k_base")

    # [수정] 파일인지 폴더인지 판단하여 목록 생성
    files_to_process = []
    root_dir = ""

    if os.path.isfile(target_path):
        # 단일 파일인 경우
        root_dir = os.path.dirname(target_path)
        files_to_process = [os.path.basename(target_path)]
    else:
        # 폴더인 경우
        root_dir = target_path
        files_to_process = [f for f in os.listdir(root_dir) if f.lower().endswith(('.txt', '.json'))]
    
    if not files_to_process:
        log_callback("!! 처리할 텍스트 파일(.txt, .json)이 없습니다.")
        return None

    # 파일 처리 루프
    for fname in files_to_process:
        full_path = os.path.join(root_dir, fname)
        try:
            with open(full_path, "r", encoding="utf-8", errors='ignore') as f:
                lines = [l for l in f.readlines() if l.strip()]
                text = "".join(lines)
            
            total_chars += len(text)
            total_lines += len(lines)
            
            if provider == "OPENAI" and enc: 
                total_tokens += len(enc.encode(text))
            else: 
                # 토크나이저가 없는 경우 대략적인 추산 (한글/영어 혼합 고려)
                total_tokens += int(len(text) / 3.0) 
                
            file_count += 1
        except Exception as e: 
            log_callback(f"!! 파일 읽기 제외 ({fname}): {e}")
            
    estimated_cost = 0.0
    estimated_time_sec = 0.0
    
    if provider == "DEEPL":
        # DeepL은 글자수 기반 (백만 자당 $25 가정)
        estimated_cost = (total_chars / 1_000_000) * 25.00
    else:
        # LLM은 토큰 기반
        in_price, out_price = pricing_engine.get_price(model)
        # 입력 비용 + 출력 비용(입력의 1.2배 길이 가정)
        input_cost = (total_tokens / 1_000_000) * in_price
        output_cost = ((total_tokens * 1.2) / 1_000_000) * out_price 
        estimated_cost = input_cost + output_cost

    # 예상 시간 (청크 단위 요청 딜레이 고려)
    CHUNK_SIZE = 20
    total_chunks = math.ceil(total_lines / CHUNK_SIZE)
    estimated_time_sec = total_chunks * 2.5 

    log_callback(f"=== [{provider}] 견적 산출 결과 ===")
    log_callback(f"• 대상: {'단일 파일' if os.path.isfile(target_path) else '폴더'}")
    log_callback(f"• 파일: {file_count}개 / 라인: {total_lines:,}줄")
    log_callback(f"• 토큰(추산): 약 {total_tokens:,} tokens")
    log_callback(f"• 예상 비용: ${estimated_cost:.4f}")
    log_callback(f"• 예상 소요 시간: 약 {timedelta(seconds=int(estimated_time_sec))}")
    
    return {"cost": estimated_cost, "time_sec": estimated_time_sec, "files": file_count, "lines": total_lines}

# ==========================================
# [메인 로직: 번역 프로세서]
# ==========================================
class TranslationProcessor:
    def __init__(self, options, log_callback, progress_callback=None):
        self.options = options
        self.log = log_callback
        self.progress = progress_callback
        self.glossary_mgr = GlossaryManager(options.get('glossary_path'))
        self.provider = self._init_provider()

        self.chunk_size = options.get('chunk_size', 15)
        self.system_prompt_base = options.get('system_prompt', "")
        self.request_delay = options.get('request_delay', 0.5)

    def _init_provider(self):
        p_name = self.options['provider']
        key = self.options['api_key']
        model = self.options['model']
        if p_name == "OPENAI": return OpenAIProvider(key, model, self.options)
        if p_name == "ANTHROPIC": return AnthropicProvider(key, model, self.options)
        if p_name == "GOOGLE": return GoogleGeminiProvider(key, model, self.options)
        if p_name == "DEEPL": return DeepLProvider(key, self.options)
        return None

    def run(self, input_path, out_target):
        """
        out_target: 사용자가 지정한 출력 경로 (파일일 수도, 폴더일 수도 있음)
        """
        if not self.provider:
            self.log("!! 공급자 초기화 실패")
            return

        self.log(">> 작업 대상 확인 중...")
        
        # [FIX] 변수 초기화 및 출력 경로 로직 개선
        is_single_file_output = False
        output_dir = "" # 출력 '폴더' 경로

        # 1. 출력 경로(out_target)가 파일인지 폴더인지 판단
        if os.path.splitext(out_target)[1]: 
            # 확장자가 있으면 파일로 간주
            is_single_file_output = True
            output_dir = os.path.dirname(out_target)
        else:
            # 확장자가 없으면 폴더로 간주
            is_single_file_output = False
            output_dir = out_target

        # 2. 출력 폴더 생성
        if output_dir and not os.path.exists(output_dir): 
            try:
                os.makedirs(output_dir)
            except Exception as e:
                self.log(f"!! 폴더 생성 실패: {e}")
                return

        # 3. 입력 파일 목록 스캔
        tasks = [] 
        total_lines_global = 0
        target_files = []
        src_root = ""

        if os.path.isfile(input_path):
            # 단일 파일 모드
            src_root = os.path.dirname(input_path)
            fname = os.path.basename(input_path)
            target_files = [fname]
            self.log(f">> [모드] 단일 파일 번역: {fname}")
        elif os.path.isdir(input_path):
            # 폴더 일괄 모드
            src_root = input_path
            target_files = [f for f in os.listdir(src_root) if f.lower().endswith(('.txt', '.json', '.ini'))]
            self.log(f">> [모드] 폴더 일괄 번역: {len(target_files)}개 파일 발견")
        else:
            self.log(f"!! 오류: 경로를 찾을 수 없습니다: {input_path}")
            return

        # 파일 읽기 및 작업 생성
        for fname in target_files:
            src_file_path = os.path.join(src_root, fname)
            try:
                with open(src_file_path, "r", encoding="utf-8", errors='replace') as f:
                    raw_lines = f.readlines()
                
                valid_lines = []
                for line in raw_lines:
                    s_line = line.strip()
                    if not s_line: continue
                    if s_line.startswith('//'): continue
                    valid_lines.append(s_line)
                
                if valid_lines:
                    total_lines_global += len(valid_lines)
                    
                    # [FIX] 개별 파일의 저장 위치 결정
                    final_out_path = ""
                    if is_single_file_output and len(target_files) == 1:
                        # 입력도 1개, 출력도 파일 지정이면 사용자가 정한 이름 그대로 사용
                        final_out_path = out_target
                    else:
                        # 그 외에는 출력 폴더 내에 원본 파일명 유지
                        final_out_path = os.path.join(output_dir, fname)

                    tasks.append({
                        'fname': fname,
                        'src': src_file_path,
                        'out': final_out_path,
                        'lines': valid_lines,
                        'raw_content': raw_lines 
                    })
            except Exception as e:
                self.log(f"!! 파일 스캔 오류 ({fname}): {e}")

        if total_lines_global == 0:
            self.log(">> 번역할 유효한 텍스트가 없습니다.")
            return

        self.log(f">> 총 {len(tasks)}개 파일, 약 {total_lines_global} 라인 처리 시작")
        self.log(f">> 설정 확인: Chunk={self.chunk_size}, Temp={self.options.get('temperature')}, JSON모드={'ON' if self.options.get('force_json') else 'OFF'}")

        current_processed_count = 0
        
        for task in tasks:
            self.log(f">> [처리 시작] {task['fname']}")
            
            current_processed_count = self._process_file_internal(
                task, current_processed_count, total_lines_global
            )

        self.log("=== 모든 작업 완료 ===")
        if self.progress: self.progress(1.0, "완료")

    def _process_file_internal(self, task, current_global_count, total_global_count):
        fname = task['fname']
        lines_to_process = task['lines']
        out_path = task['out']
        
        translation_map = {}
        
        CHUNK_SIZE = self.chunk_size
        SYSTEM_PROMPT_BASE = self.system_prompt_base

        for i in range(0, len(lines_to_process), CHUNK_SIZE):
            chunk = lines_to_process[i:i + CHUNK_SIZE]
            
            try:
                chunk_data = []
                chunk_map = {} 
                
                for idx, line in enumerate(chunk):
                    local_id = idx + 1
                    
                    if '=' in line:
                        clean_text = line.split('=', 1)[0].strip()
                    else:
                        clean_text = line.strip()

                    # [수정] 옵션에 따라 마스킹 적용 여부 결정
                    if self.options.get('auto_mask', True):
                        # 마스킹 적용
                        masked_text, active_masks = self.glossary_mgr.apply_masking(clean_text)
                    else:
                        # 마스킹 미적용 (원문 그대로 사용)
                        masked_text = clean_text
                        active_masks = {}

                    chunk_data.append({"id": local_id, "text": masked_text})
                    chunk_map[local_id] = {"orig": clean_text, "masks": active_masks}

                context_hint = ""
                for c_item in chunk_data:
                    masks = chunk_map[c_item['id']]['masks']
                    if masks:
                        for t, info in masks.items():
                            if info['hint']:
                                context_hint += f"Reference: {t} means {info['tgt']} (Context: {info['hint']})\n"
                            else:
                                context_hint += f"Reference: {t} means {info['tgt']}\n"

                final_system_prompt = SYSTEM_PROMPT_BASE + context_hint
                
                input_json = json.dumps(chunk_data, ensure_ascii=False)
                
                response_text = self.provider.translate(final_system_prompt, input_json)
                
                try:
                    clean_json = re.sub(r"```json|```", "", response_text).strip()
                    if clean_json:
                        translated_list = json.loads(clean_json)
                        if isinstance(translated_list, dict): translated_list = [translated_list]
                        
                        for item in translated_list:
                            lid = item.get('id')
                            trans_text = item.get('trans')
                            
                            if lid in chunk_map and trans_text:
                                orig_info = chunk_map[lid]
                                # 옵션 키 'auto_restore'가 없으면 기본값 True (기존 동작 유지)
                                if self.options.get('auto_restore', True):
                                    final_trans = self.glossary_mgr.restore_masking(trans_text, orig_info['masks'])
                                else:
                                    # 해제하지 않고 저장
                                    final_trans = trans_text
                                translation_map[orig_info['orig']] = final_trans
                except json.JSONDecodeError:
                    self.log(f"!! JSON 파싱 실패 (청크 {i//CHUNK_SIZE}). 원문 유지.")

            except Exception as e:
                self.log(f"!! 청크 처리 중 오류: {e}")
                time.sleep(1)

            current_global_count += len(chunk)
            if self.progress and total_global_count > 0:
                ratio = current_global_count / total_global_count
                self.progress(ratio, f"{fname} 처리 중")
            
            time.sleep(self.request_delay)

        try:
            final_results = []
            for line in task['raw_content']:
                line_stripped = line.strip()
                if not line_stripped or line_stripped.startswith('//'):
                    final_results.append(line_stripped)
                    continue
                
                if '=' in line_stripped:
                    key_part = line_stripped.split('=', 1)[0].strip()
                else:
                    key_part = line_stripped
                
                if key_part in translation_map:
                    final_results.append(f"{key_part}={translation_map[key_part]}")
                else:
                    final_results.append(f"{key_part}={key_part}")
            
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("\n".join(final_results))

        except Exception as e:
            self.log(f"!! 파일 저장 실패: {e}")

        return current_global_count

class GlossaryManager:
    def __init__(self, glossary_path):
        # utils의 표준 로더 사용 (mask_id 형식 통일)
        self.term_map = utils.load_glossary_data(glossary_path)
    
    def apply_masking(self, text):
        active_masks = {}
        masked_text = text
        
        # utils에서 로드된 mask_id (__MSK_XXXX__) 사용
        for item in self.term_map:
            src = item['src']
            mask_id = item['mask_id']
            if src in masked_text:
                masked_text = masked_text.replace(src, mask_id)
                active_masks[mask_id] = item
                
        return masked_text, active_masks

    def restore_masking(self, text, active_masks):
        restored = text
        # 번역 결과를 복원하므로 item['tgt'] (번역문) 사용
        for token, info in active_masks.items():
            restored = restored.replace(token, info['tgt'])
        return restored

# ==========================================
# [인터페이스 함수]
# ==========================================
def process_ai_translation(src_dir, out_dir, options, log_callback, progress_callback=None):
    processor = TranslationProcessor(options, log_callback, progress_callback)
    processor.run(src_dir, out_dir)

def process_cost_estimation(src_dir, provider, model, log_callback):
    return calculate_estimates(src_dir, provider, model, log_callback)