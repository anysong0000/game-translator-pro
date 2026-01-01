# -*- coding: utf-8 -*-
"""
Project: Game Translator Pro
Author: anysong
Copyright: Copyright © 2025 anysong. All rights reserved.
License: CC BY-NC-ND 4.0 (Attribution-NonCommercial-NoDerivs)

[Disclaimer]
1. 본 프로그램은 에셋 추출 도구(UABEA, dnSpy 등)와 연동하여 사용하는 '중개 보조 도구'입니다.
2. 프로그램 사용으로 인한 게임 계정 제재, 데이터 손상 등의 책임은 전적으로 사용자에게 있습니다.
3. 상업적 이용을 금하며, 반드시 원본 파일의 백업 후 사용을 권장합니다.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import threading
import configparser
import sys

# 모듈 가져오기 (사용자 기존 모듈 유지)
import logic
import logic_ai 
import utils

# ==========================================
# 설정 및 상수
# ==========================================
WINDOW_TITLE = "Game Translator Pro v1.11"
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")

# 기본 프롬프트
DEFAULT_PROMPT = (
    "You are a professional game translator.\n"
    "Output must be a JSON array of objects. Format: [{\"id\": 1, \"trans\": \"Korean text\"}, ...]\n"
    "Do NOT translate tokens like __MASK_XXXX__.\n"
    "Translate the 'text' field into natural Korean 'trans'."
)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class TranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("1050x800")

        try:
            self.iconbitmap(os.path.join(BASE_DIR, "translator_icon.ico"))
        except:
            pass
        
        # [레이아웃 그리드 설정]
        # column 0: 사이드바 (고정 폭)
        # column 1: 메인 콘텐츠 (확장)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1) # 메인 콘텐츠 영역

        self.init_variables()
        self.load_config()
        
        # UI 구성요소 초기화
        self.setup_sidebar()
        self.setup_main_container()
        self.setup_log_panel()
        
        # 초기 화면 로드 (워크플로우)
        self.select_frame_by_name("workflow")
        
        # 초기 모델 목록 설정
        self.refresh_model_list(init=True)

    def init_variables(self):
        self.path_src = tk.StringVar()
        self.path_out = tk.StringVar()
        self.path_db = tk.StringVar()
        self.path_glossary = tk.StringVar()
        self.path_util_db = tk.StringVar()
        self.path_ai_input = tk.StringVar()
        self.path_mask_target = tk.StringVar()
        
        self.opt_group_brackets = tk.BooleanVar(value=True)
        self.opt_extract_masking = tk.BooleanVar(value=False)
        
        self.db_format = tk.StringVar(value="자동감지 (Auto)")
        if not hasattr(self, 'val_newline'): self.val_newline = tk.StringVar(value="[ENTER]")
        if not hasattr(self, 'val_space'): self.val_space = tk.StringVar(value="[NBSP]")

        self.opt_smart_mode = tk.BooleanVar(value=True)
        self.opt_smart_save = tk.BooleanVar(value=True)
        self.key_newline = tk.StringVar(value="\\n")
        self.key_space = tk.StringVar(value=" ")
        self.val_newline = tk.StringVar(value="[ENTER]")
        self.val_space = tk.StringVar(value="[NBSP]")
        
        self.tag_preset = tk.StringVar(value="Unity (<...>)")
        self.tag_custom_pattern = tk.StringVar(value="")
        
        self.ai_provider = tk.StringVar(value="OPENAI")
        self.ai_api_key = tk.StringVar()
        self.ai_model = tk.StringVar(value="gpt-4o-mini")

        self.ai_chunk_size = tk.IntVar(value=15)
        self.ai_temperature = tk.DoubleVar(value=0.1)
        self.ai_force_json = tk.BooleanVar(value=True)
        self.ai_request_delay = tk.DoubleVar(value=0.5)
        self.ai_auto_mask = tk.BooleanVar(value=True)
        self.ai_auto_restore = tk.BooleanVar(value=True)

        self.opt_smart_header = tk.BooleanVar(value=True)  # 헤더 보호
#        self.opt_smart_json = tk.BooleanVar(value=True)    # JSON 문법 교정
        self.opt_smart_special = tk.BooleanVar(value=True) # 특수문자 처리
        self.opt_safe_english = tk.BooleanVar(value=False)

    # ================================================================
    # [UI Part 1] 사이드바 (Navigation)
    # ================================================================
    def setup_sidebar(self):
        self.sidebar_frame = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1) # 하단 공백용

        # 1. 로고 영역
        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Game Trans\nPro", 
                                     font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # 2. 네비게이션 버튼들
        self.nav_buttons = {}
        
        btn_data = [
            ("workflow", "🏠 워크플로우"),
            ("project", "📁 프로젝트 설정"),
            ("ai_conf", "🤖 AI 설정"),
            ("advanced", "🔧 고급 설정"),
            ("help", "❓ 도움말"),
            ("info", "ℹ️ 정보")
        ]
        
        for i, (name, text) in enumerate(btn_data):
            btn = ctk.CTkButton(self.sidebar_frame, corner_radius=0, height=40, border_spacing=10, 
                                text=text, fg_color="transparent", text_color=("gray10", "gray90"), 
                                hover_color=("gray70", "gray30"), anchor="w", 
                                command=lambda n=name: self.select_frame_by_name(n))
            btn.grid(row=i+1, column=0, sticky="ew")
            self.nav_buttons[name] = btn

        # 3. 사이드바 하단 (테마/정보)
        switch_theme = ctk.CTkSwitch(self.sidebar_frame, text="Dark Mode", command=self.toggle_theme)
        switch_theme.select()
        switch_theme.grid(row=6, column=0, padx=20, pady=20, sticky="s")

    def toggle_theme(self):
        if ctk.get_appearance_mode() == "Dark":
            ctk.set_appearance_mode("Light")
        else:
            ctk.set_appearance_mode("Dark")

    # ================================================================
    # [UI Part 2] 메인 컨테이너 및 페이지 전환 로직
    # ================================================================
    def setup_main_container(self):
        # [FIX 2] 눈뽕 방지: 라이트 모드 배경을 'transparent'(흰색) 대신 부드러운 회색('gray90')으로 설정
        bg_color = ("gray90", "gray17")
        
        # 오른쪽 영역 (콘텐츠가 들어갈 자리)
        # row=0: 메인 페이지들, row=1: 로그 패널
        self.main_container = ctk.CTkFrame(self, fg_color=bg_color)
        self.main_container.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)

        # 페이지 프레임들을 미리 생성해둡니다.
        self.frames = {}
        
        # 각 페이지 프레임의 배경도 부드러운 톤에 맞춤
        frame_bg = "transparent"

        self.frames["workflow"] = ctk.CTkFrame(self.main_container, fg_color=frame_bg)
        self.setup_page_workflow(self.frames["workflow"])
        
        self.frames["project"] = ctk.CTkFrame(self.main_container, fg_color=frame_bg)
        self.setup_page_project(self.frames["project"])
        
        self.frames["ai_conf"] = ctk.CTkFrame(self.main_container, fg_color=frame_bg)
        self.setup_page_ai(self.frames["ai_conf"])

        self.frames["advanced"] = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        self.setup_page_advanced(self.frames["advanced"])

        self.frames["help"] = ctk.CTkFrame(self.main_container, fg_color=frame_bg)
        self.setup_page_help(self.frames["help"])

        self.frames["info"] = ctk.CTkFrame(self.main_container, fg_color=frame_bg)
        self.setup_page_info(self.frames["info"])

    def select_frame_by_name(self, name):
        # 1. 모든 버튼 색상 초기화
        for btn_name, btn in self.nav_buttons.items():
            btn.configure(fg_color="transparent")
        
        # 2. 선택된 버튼 강조
        if name in self.nav_buttons:
            self.nav_buttons[name].configure(fg_color=("gray75", "gray25"))
        
        # 3. 모든 프레임 숨기기 (grid_forget)
        for frame in self.frames.values():
            frame.grid_forget()
            
        # 4. 선택된 프레임 표시
        if name in self.frames:
            self.frames[name].grid(row=0, column=0, sticky="nsew")

    # ================================================================
    # [UI Part 3] 각 페이지별 UI 구성
    # ================================================================
    
    # --- 1. 워크플로우 (대시보드) ---
    def setup_page_workflow(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_columnconfigure(2, weight=1)
        
        # 카드 1: 추출
        card1 = self.create_workflow_card(parent, "STEP 1. 텍스트 추출", "#E67E22", 0)
        ctk.CTkCheckBox(card1, text="대사 괄호 「...」 보호", variable=self.opt_group_brackets).pack(anchor="w", padx=15, pady=5)
        ctk.CTkCheckBox(card1, text="용어집 마스킹 적용", variable=self.opt_extract_masking).pack(anchor="w", padx=15, pady=5)
        ctk.CTkLabel(card1, text="", height=20).pack(expand=True) # Spacer
        self.btn_extract = ctk.CTkButton(card1, text="▶ 추출 시작", command=self.run_extract, fg_color="#E67E22", height=40)
        self.btn_extract.pack(fill="x", padx=15, pady=20, side="bottom")

        # 카드 2: AI 번역
        card2 = self.create_workflow_card(parent, "STEP 2. AI 초벌 번역", "#8E44AD", 1)
        ctk.CTkLabel(card2, text="번역 대상 (비워두면 전체):", font=("Arial", 12)).pack(anchor="w", padx=15, pady=(10, 0))
        
        input_box = ctk.CTkFrame(card2, fg_color="transparent")
        input_box.pack(fill="x", padx=15, pady=5)
        ctk.CTkEntry(input_box, textvariable=self.path_ai_input, placeholder_text="특정 파일 선택...").pack(side="left", fill="x", expand=True)
        ctk.CTkButton(input_box, text="📂", width=30, command=lambda: self.browse_path(self.path_ai_input, False)).pack(side="left", padx=(5,0))
        
        ctk.CTkLabel(card2, text="현재 모델:", font=("Arial", 12)).pack(anchor="w", padx=15)
        ctk.CTkEntry(card2, textvariable=self.ai_model, state="disabled", 
                     fg_color=("white", "#333"), 
                     text_color=("black", "white")).pack(fill="x", padx=15, pady=(0, 10))
        
        self.btn_ai = ctk.CTkButton(card2, text="▶ AI 번역 시작", command=self.run_ai_translate, fg_color="#8E44AD", height=50, font=("Arial", 14, "bold"))
        self.btn_ai.pack(fill="x", padx=15, pady=20, side="bottom")

        # 카드 3: 적용
        card3 = self.create_workflow_card(parent, "STEP 3. 적용 파일 생성", "#27AE60", 2)
        ctk.CTkLabel(card3, text="번역된 DB 파일:", font=("Arial", 12)).pack(anchor="w", padx=15, pady=(10, 0))
        
        db_box = ctk.CTkFrame(card3, fg_color="transparent")
        db_box.pack(fill="x", padx=15, pady=5)
        ctk.CTkEntry(db_box, textvariable=self.path_db).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(db_box, text="📂", width=30, command=lambda: self.browse_path(self.path_db, False)).pack(side="left", padx=(5,0))
        
        ctk.CTkCheckBox(card3, text="스마트 모드 (권장)", variable=self.opt_smart_mode).pack(anchor="w", padx=15, pady=5)
        ctk.CTkCheckBox(card3, text="스마트 저장", variable=self.opt_smart_save).pack(anchor="w", padx=15, pady=5)
        
        self.btn_apply = ctk.CTkButton(card3, text="▶ 적용 시작", command=self.run_translate, fg_color="#27AE60", height=40)
        self.btn_apply.pack(fill="x", padx=15, pady=20, side="bottom")

    def create_workflow_card(self, parent, title, color, col_idx):
        # [FIX 2 연동] 카드의 배경색도 라이트 모드 시 너무 밝지 않게 조정 (자동 테마 적용되지만 대비를 위해)
        frame = ctk.CTkFrame(parent, corner_radius=15, border_width=2, border_color="#444")
        frame.grid(row=0, column=col_idx, sticky="nsew", padx=10, pady=20)
        
        # Header
        header = ctk.CTkLabel(frame, text=title, font=("Arial", 16, "bold"), text_color=color)
        header.pack(pady=15)
        tk.Frame(frame, height=1, bg="#555").pack(fill="x", padx=10, pady=(0, 10))
        return frame

    # --- 2. 프로젝트 설정 ---
    def setup_page_project(self, parent):
        ctk.CTkLabel(parent, text="프로젝트 경로 설정", font=("Arial", 20, "bold")).pack(anchor="w", padx=20, pady=20)
        
        container = ctk.CTkFrame(parent)
        container.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        self.create_path_row(container, "원본 폴더 (Source):", self.path_src, is_folder=True, desc="게임의 원본 assets 혹은 텍스트 파일이 있는 폴더")
        self.create_path_row(container, "저장 폴더 (Output):", self.path_out, is_folder=True, desc="추출된 텍스트와 번역 결과물이 저장될 폴더")
        self.create_path_row(container, "용어집 (Glossary):", self.path_glossary, is_folder=False, desc="고유명사 번역을 고정할 CVB/TXT 파일")
        btn_sample = ctk.CTkButton(container, text="📘 용어집 샘플 양식 생성", 
                                  command=self.generate_sample_glossary, 
                                  fg_color="#5D6D7E", width=200)
        btn_sample.pack(pady=10)
        
        ctk.CTkLabel(container, text="* 경로는 자동으로 저장됩니다.", text_color="gray").pack(pady=20)

    # --- 3. AI 설정 ---
    def setup_page_ai(self, parent):
        ctk.CTkLabel(parent, text="AI API 및 모델 설정", font=("Arial", 20, "bold")).pack(anchor="w", padx=20, pady=20)
        
        # 설정 폼
        form = ctk.CTkFrame(parent)
        form.pack(fill="x", padx=20, pady=10)
        
        # Provider
        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(row1, text="서비스 공급자:", width=100, anchor="w").pack(side="left")
        self.cbo_provider = ctk.CTkOptionMenu(row1, variable=self.ai_provider, 
                                              values=list(logic_ai.PROVIDER_MODELS.keys()),
                                              command=self.on_provider_change, width=200)
        self.cbo_provider.pack(side="left")

        # API Key
        row2 = ctk.CTkFrame(form, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(row2, text="API Key:", width=100, anchor="w").pack(side="left")
        ctk.CTkEntry(row2, textvariable=self.ai_api_key, show="*", width=300).pack(side="left")
        
        # Model
        row3 = ctk.CTkFrame(form, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(row3, text="사용 모델:", width=100, anchor="w").pack(side="left")
        self.cbo_model = ctk.CTkOptionMenu(row3, variable=self.ai_model, values=[])
        self.cbo_model.pack(side="left")
        
        # 비용 및 가격 갱신 도구
        tool_frame = ctk.CTkFrame(parent)
        tool_frame.pack(fill="x", padx=20, pady=20)
        ctk.CTkLabel(tool_frame, text="비용 관리 및 도구", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=10)
        
        # [추가] 비용 산출 대상 선택 UI
        target_row = ctk.CTkFrame(tool_frame, fg_color="transparent")
        target_row.pack(fill="x", padx=10, pady=(0, 5))
        
        ctk.CTkLabel(target_row, text="계산 대상:", width=80, anchor="w").pack(side="left", padx=(10, 0))
        ctk.CTkEntry(target_row, textvariable=self.path_ai_input, placeholder_text="워크플로우의 '번역 대상'과 연동됩니다.").pack(side="left", fill="x", expand=True)
        
        # 파일/폴더 선택 버튼
        ctk.CTkButton(target_row, text="📄 파일", width=50, 
                      command=lambda: self.browse_path(self.path_ai_input, False),
                      fg_color="#555").pack(side="left", padx=2)
        ctk.CTkButton(target_row, text="📁 폴더", width=50, 
                      command=lambda: self.browse_path(self.path_ai_input, True),
                      fg_color="#555").pack(side="left", padx=2)

        btn_box = ctk.CTkFrame(tool_frame, fg_color="transparent")
        btn_box.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(btn_box, text="🔄 가격표 갱신 (Web)", command=self.update_price_data, fg_color="#34495E").pack(side="left", padx=5)
        ctk.CTkButton(btn_box, text="💸 예상 비용 산출 (전체 스캔)", command=self.run_cost_estimation, fg_color="#2980B9").pack(side="left", padx=5)

    def run_masking_apply(self):
        target_file = self.path_mask_target.get()
        glossary_file = self.path_glossary.get()

        if not self._check_masking_files(target_file, glossary_file): return

        if not messagebox.askyesno("확인", "파일 내용을 마스킹 처리하시겠습니까?\n(원문 → Mask ID)"):
            return

        # UI 멈춤 방지를 위해 스레드로 logic 함수 호출
        self.log(f">> 마스킹 적용 시작...")
        self.wrap_thread(
            logic.process_db_masking, 
            target_file, 
            glossary_file, 
            'apply', 
            self.log
        )

    def run_masking_release(self):
        target_file = self.path_mask_target.get()
        glossary_file = self.path_glossary.get()

        if not self._check_masking_files(target_file, glossary_file): return

        msg = (
            "마스킹을 해제하고 번역을 적용하시겠습니까?\n\n"
            "[작동 방식]\n"
            "좌변 (= 왼쪽) : 용어집의 '원문'으로 복원\n"
            "우변 (= 오른쪽) : 용어집의 '번역문'으로 치환"
        )
        if not messagebox.askyesno("확인", msg):
            return

        # UI 멈춤 방지를 위해 스레드로 logic 함수 호출
        self.log(f">> 마스킹 해제 및 번역 적용 시작...")
        self.wrap_thread(
            logic.process_db_masking, 
            target_file, 
            glossary_file, 
            'restore', 
            self.log
        )

    # [헬퍼] 파일 유효성 검사
    def _check_masking_files(self, target, glossary):
        if not target or not os.path.exists(target):
            messagebox.showerror("오류", "대상 파일을 선택해주세요.")
            return False
        if not glossary or not os.path.exists(glossary):
            messagebox.showerror("오류", "프로젝트 설정에서 '용어집'을 먼저 설정해주세요.")
            return False
        return True

    # [헬퍼] 파일 저장 및 알림
    def _save_masked_file(self, original_path, content, suffix, msg):
        dir_name = os.path.dirname(original_path)
        base_name = os.path.splitext(os.path.basename(original_path))[0]
        
        # 파일명 중복 방지를 위해 기존 suffix 제거 시도
        if base_name.endswith("_MASKED"): base_name = base_name.replace("_MASKED", "")
        if base_name.endswith("_UNMASKED"): base_name = base_name.replace("_UNMASKED", "")
            
        save_path = os.path.join(dir_name, f"{base_name}{suffix}")

        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(content)

        self.log(f">> {msg}")
        messagebox.showinfo("완료", f"{msg}\n저장 경로: {save_path}")
        os.startfile(dir_name)

    def update_format_preview(self, choice):
        """
        [직관적 확인 기능]
        선택된 모드에 따라 줄바꿈(\n)과 공백이 최종적으로 어떻게 변하는지 표시합니다.
        """
        preview_text = ""
        is_custom = False
        text_color = "gray70" # 기본 색상

        if "자동감지" in choice:
            preview_text = "ℹ️ 파일 확장자(.json / .txt)에 따라 아래 모드 중 하나가 자동 적용됩니다."
            text_color = "#3498DB" # 파란색 계열 (정보)
            
        elif "TXT" in choice:
            # TXT: 실제 줄바꿈이 일어남을 강조
            preview_text = "✅ 줄바꿈 ➔ 실제 엔터(↵)   |   ✅ 공백 ➔ 특수공백(NBSP)"
            text_color = "#2ECC71" # 초록색 계열 (적용)
            
        elif "JSON" in choice:
            # JSON: 이스케이프 문자(\n)로 유지됨을 강조
            preview_text = "✅ 줄바꿈 ➔ 문자열(\\\\n)   |   ✅ 공백 ➔ 실제 스페이스( )"
            text_color = "#E67E22" # 주황색 계열 (주의)
            
        elif "사용자지정" in choice:
            preview_text = "⚙️ 아래 입력칸(커스텀 설정)에 지정된 값으로 치환됩니다."
            is_custom = True
            text_color = "#9B59B6" # 보라색 계열 (커스텀)
        
        # 1. 프리뷰 텍스트 및 색상 갱신
        self.lbl_format_preview.configure(text=preview_text, text_color=text_color)
        
        # 2. 커스텀 입력창 활성/비활성 제어
        state = "normal" if is_custom else "disabled"
        
        # 비활성화 시 텍스트 색상을 흐리게 처리
        entry_text_color = ("black", "white") if is_custom else "gray50"
        
        self.entry_custom_nl.configure(state=state, text_color=entry_text_color)
        self.entry_custom_sp.configure(state=state, text_color=entry_text_color)

    # --- 4. 고급 설정 ---
    def setup_page_advanced(self, parent):

        # [신규 섹션] 스마트 모드 세부 설정
        frame_smart = ctk.CTkFrame(parent)
        frame_smart.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(frame_smart, text="⚡ 스마트 모드 세부 설정", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        
        smart_grid = ctk.CTkFrame(frame_smart, fg_color="transparent")
        smart_grid.pack(fill="x", padx=10, pady=5)
        
        # 체크박스 3개 배치
        ctk.CTkCheckBox(smart_grid, text="헤더 보호 (바이너리 깨짐 방지)", variable=self.opt_smart_header).pack(anchor="w", pady=2)
        ctk.CTkCheckBox(smart_grid, text="특수문자 처리 (엔터/공백 변환)", variable=self.opt_smart_special).pack(anchor="w", pady=2)
        safe_chk = ctk.CTkCheckBox(smart_grid, text="순수 영문 보호 모드 (변수 오역 방지 / 속도 느림)", 
                                   variable=self.opt_safe_english, text_color="#E74C3C") # 붉은색 강조
        safe_chk.pack(anchor="w", pady=2)

        # [신규 섹션] DB 포맷 및 파싱 설정
        frame_fmt = ctk.CTkFrame(parent)
        frame_fmt.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(frame_fmt, text="📁 DB 포맷 및 파싱 설정", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        
        # --- [Row 1] 처리 모드 선택 & 직관적 프리뷰 ---
        row_mode = ctk.CTkFrame(frame_fmt, fg_color="transparent")
        row_mode.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(row_mode, text="처리 모드:", width=80, anchor="w").pack(side="left", padx=5)
        
        format_options = ["자동감지 (Auto)", "사용자지정 (Custom)"]
        self.cbo_format = ctk.CTkOptionMenu(
            row_mode, variable=self.db_format, values=format_options, width=160,
            command=self.update_format_preview # 선택 시 프리뷰 갱신
        )
        self.cbo_format.pack(side="left", padx=5)

        # [프리뷰 라벨] 줄바꿈/띄어쓰기 변화를 보여주는 텍스트
        self.lbl_format_preview = ctk.CTkLabel(row_mode, text="", font=("Consolas", 12, "bold"))
        self.lbl_format_preview.pack(side="left", padx=15)

        # --- [Row 2] 커스텀 입력 필드 (하단 배치 - 들여쓰기 효과) ---
        self.row_custom = ctk.CTkFrame(frame_fmt, fg_color="transparent")
        self.row_custom.pack(fill="x", padx=10, pady=(0, 10))

        # '└─' 기호로 하위 메뉴임을 표현
        icon_label = ctk.CTkLabel(self.row_custom, text="└─ [커스텀 설정]", text_color="gray", width=100, anchor="e")
        icon_label.pack(side="left", padx=(5, 5))
        
        # 줄바꿈 입력
        ctk.CTkLabel(self.row_custom, text="줄바꿈 치환:").pack(side="left", padx=5)
        self.entry_custom_nl = ctk.CTkEntry(self.row_custom, textvariable=self.val_newline, width=80, placeholder_text="\\n")
        self.entry_custom_nl.pack(side="left")
        
        # 공백 입력
        ctk.CTkLabel(self.row_custom, text="공백 치환:").pack(side="left", padx=5)
        self.entry_custom_sp = ctk.CTkEntry(self.row_custom, textvariable=self.val_space, width=80, placeholder_text="[NBSP]")
        self.entry_custom_sp.pack(side="left")

        # 초기 실행 시 프리뷰 상태 업데이트 (기본값 반영)
        self.update_format_preview(self.db_format.get())

        # 섹션 1: AI 튜닝
        frame_ai = ctk.CTkFrame(parent)
        frame_ai.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(frame_ai, text="🧠 AI 동작 튜닝 (Prompt & Params)", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        
        grid = ctk.CTkFrame(frame_ai, fg_color="transparent")
        grid.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(grid, text="청크(줄 수):").pack(side="left", padx=5)
        ctk.CTkEntry(grid, textvariable=self.ai_chunk_size, width=50).pack(side="left")
        ctk.CTkLabel(grid, text="Temperature:").pack(side="left", padx=5)
        ctk.CTkEntry(grid, textvariable=self.ai_temperature, width=50).pack(side="left")
        ctk.CTkLabel(grid, text="Delay(초):").pack(side="left", padx=5)
        ctk.CTkEntry(grid, textvariable=self.ai_request_delay, width=50).pack(side="left")
        ctk.CTkCheckBox(grid, text="JSON 강제", variable=self.ai_force_json).pack(side="left", padx=15)
        # 1. 번역 전 적용
        ctk.CTkCheckBox(grid, text="마스킹 전처리", variable=self.ai_auto_mask).pack(side="left", padx=5)
        # 2. 번역 후 해제
        ctk.CTkCheckBox(grid, text="마스킹 후처리", variable=self.ai_auto_restore).pack(side="left", padx=5)
        prompt_header = ctk.CTkFrame(frame_ai, fg_color="transparent")
        prompt_header.pack(fill="x", padx=10, pady=(10, 0))
        
        ctk.CTkLabel(prompt_header, text="System Prompt:", anchor="w", font=("Arial", 12, "bold")).pack(side="left")
        
        ctk.CTkButton(prompt_header, text="🔍 크게 보기 / 편집 (Popup)", 
                      width=120, height=24, 
                      fg_color="#5D6D7E", 
                      command=self.open_prompt_editor).pack(side="right")

        self.txt_prompt = ctk.CTkTextbox(frame_ai, height=100, font=("Consolas", 12)) # 기본 크기
        self.txt_prompt.pack(fill="x", padx=10, pady=5)
        self.txt_prompt.insert("1.0", DEFAULT_PROMPT)
        
        # 섹션 2: DB 및 Regex
        frame_rule = ctk.CTkFrame(parent)
        frame_rule.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(frame_rule, text="🛡️ 태그 보호 및 포맷", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        
        rule_row = ctk.CTkFrame(frame_rule, fg_color="transparent")
        rule_row.pack(fill="x", padx=10, pady=5)
        
        # [FIX 1] 사라졌던 "RPG Maker" 옵션 복구
        self.tag_menu = ctk.CTkOptionMenu(rule_row, variable=self.tag_preset, 
                                          values=["Unity (<...>)", "Ren'Py ({...})", "RPG Maker (\\...)", "사용자지정(Regex)"],
                                          command=self.update_tag_ui_state)
        self.tag_menu.pack(side="left")
        self.entry_tag_custom = ctk.CTkEntry(rule_row, textvariable=self.tag_custom_pattern, placeholder_text="Regex", state="disabled")
        self.entry_tag_custom.pack(side="left", padx=5, fill="x", expand=True)

        frame_tool = ctk.CTkFrame(parent)
        frame_tool.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(frame_tool, text="🛠️ 독립형 용어집 마스킹 (File Utility)", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=10)
        
        desc = "용어집(Glossary)을 사용하여 텍스트 파일 내의 특정 단어를 치환하거나 복원합니다."
        ctk.CTkLabel(frame_tool, text=desc, text_color="gray", font=("Arial", 12)).pack(anchor="w", padx=10, pady=(0, 5))

        # 입력 파일 선택 UI
        tool_row = ctk.CTkFrame(frame_tool, fg_color="transparent")
        tool_row.pack(fill="x", padx=10, pady=10)
        
        self.entry_mask_target = ctk.CTkEntry(
            tool_row, 
            textvariable=self.path_mask_target, 
            placeholder_text="작업할 텍스트 파일 선택 (.txt)"
        )
        self.entry_mask_target.pack(side="left", fill="x", expand=True)
        
        ctk.CTkButton(
            tool_row, text="📂", width=40, 
            command=lambda: self.browse_path(self.path_mask_target, False)
        ).pack(side="left", padx=5)

        # [수정] 버튼 2개 배치 (적용 / 해제)
        btn_grid = ctk.CTkFrame(frame_tool, fg_color="transparent")
        btn_grid.pack(fill="x", padx=10, pady=(0, 15))
        
        # 적용 버튼 (원문 -> 마스킹)
        ctk.CTkButton(
            btn_grid, text="🔒 마스킹 적용 (Apply)", 
            fg_color="#D35400", hover_color="#A04000",
            command=self.run_masking_apply
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        # 해제 버튼 (마스킹 -> 원문/번역 복원)
        ctk.CTkButton(
            btn_grid, text="🔓 마스킹 해제 (Release)", 
            fg_color="#27AE60", hover_color="#1E8449",
            command=self.run_masking_release
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

        frame_appearance = ctk.CTkFrame(parent)
        frame_appearance.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(frame_appearance, text="🎨 화면 배율 및 테마 (UI Scaling)", font=("Arial", 14, "bold")).pack(anchor="w", padx=10, pady=5)
        
        app_row = ctk.CTkFrame(frame_appearance, fg_color="transparent")
        app_row.pack(fill="x", padx=10, pady=5)

        # 1. 화면 배율 (Zoom)
        ctk.CTkLabel(app_row, text="화면 크기(Zoom):").pack(side="left", padx=(5, 0))

        def change_scaling(new_scaling: str):
            new_scaling_float = int(new_scaling.replace("%", "")) / 100
            ctk.set_widget_scaling(new_scaling_float)
            # 윈도우 크기도 배율에 맞춰 살짝 조절 (선택사항)
            # ctk.set_window_scaling(new_scaling_float)

        scaling_option = ctk.CTkOptionMenu(app_row, values=["80%", "90%", "100%", "110%", "120%", "150%"],
                                           command=change_scaling)
        scaling_option.pack(side="left", padx=10)
        scaling_option.set("100%") # 기본값

        # 초기화 버튼
        ctk.CTkButton(parent, text="🔄 공장 초기화 (설정 리셋)", fg_color="#C0392B", command=self.reset_to_defaults).pack(pady=20)

    def open_prompt_editor(self):
        # 1. 새 창 생성 (Toplevel)
        editor = ctk.CTkToplevel(self)
        editor.title("System Prompt Editor")
        editor.geometry("900x700")
        
        # 모달 창 설정 (이 창이 닫힐 때까지 뒤쪽 클릭 방지 - 선택사항)
        editor.grab_set() 
        editor.focus_force()

        # 2. 상단 툴바 (폰트 조절 슬라이더 및 저장 버튼)
        toolbar = ctk.CTkFrame(editor, height=50)
        toolbar.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(toolbar, text="글자 크기:", font=("Arial", 12)).pack(side="left", padx=(10, 5))
        
        # 폰트 크기 변수
        font_size_var = ctk.IntVar(value=14)

        # [슬라이더] 수동 조절 기능
        slider = ctk.CTkSlider(toolbar, from_=10, to=40, variable=font_size_var, width=200)
        slider.pack(side="left", padx=10)
        
        lbl_size_num = ctk.CTkLabel(toolbar, text="14px", width=40)
        lbl_size_num.pack(side="left")

        # 저장 및 닫기 버튼
        def save_and_close():
            # 팝업의 내용을 메인 화면으로 복사
            content = txt_editor.get("1.0", "end-1c")
            self.txt_prompt.delete("1.0", "end")
            self.txt_prompt.insert("1.0", content)
            editor.destroy()

        ctk.CTkButton(toolbar, text="💾 적용 및 닫기", fg_color="#27AE60", 
                      command=save_and_close).pack(side="right", padx=10)

        # 3. 메인 텍스트 에디터
        txt_editor = ctk.CTkTextbox(editor, font=("Consolas", 14), wrap="word")
        txt_editor.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 메인 화면의 내용을 가져옴
        current_text = self.txt_prompt.get("1.0", "end-1c")
        txt_editor.insert("1.0", current_text)

        # 4. 기능 구현 함수들
        def update_font(val=None):
            # 슬라이더 값에 따라 폰트 변경
            size = int(font_size_var.get())
            txt_editor.configure(font=("Consolas", size))
            lbl_size_num.configure(text=f"{size}px")

        def mouse_wheel_zoom(event):
            # Ctrl 키를 누른 상태에서 휠을 굴렸을 때
            current = font_size_var.get()
            if event.delta > 0: # 휠 올림
                new_size = min(current + 2, 40)
            else: # 휠 내림
                new_size = max(current - 2, 10)
            
            font_size_var.set(new_size)
            update_font()

        # 5. 이벤트 바인딩
        slider.configure(command=update_font) # 슬라이더 움직임 감지
        
        # 텍스트 박스에 Ctrl + 마우스휠 바인딩
        # (Windows: <Control-MouseWheel>, Linux: <Control-Button-4/5> 등 차이가 있으나 Windows 기준 작성)
        txt_editor.bind("<Control-MouseWheel>", mouse_wheel_zoom)

        # --- 5. 도움말 탭 ---
    def setup_page_help(self, parent):
        ctk.CTkLabel(parent, text="사용 가이드 (User Guide)", font=("Arial", 20, "bold")).pack(anchor="w", padx=20, pady=20)
        
        help_textbox = ctk.CTkTextbox(parent, font=("Malgun Gothic", 14), height=400)
        help_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        guide_text = """
[필독: 사용 전 주의사항]
본 프로그램은 '데이터 가공 및 번역 보조 도구'입니다.
반드시 UABEA, dnSpy 등으로 에셋을 먼저 추출한 뒤 사용하십시오.

[STEP 1] 번역 데이터 추출
- 원본 폴더: 추출된 에셋들이 담긴 폴더 지정
- 결과: 번역용 통합 파일 생성 (형식: 원문=)

[STEP 2] AI 초벌 번역
- 마스킹 기능을 통해 게임 태그 및 고유명사 보호 가능
- 마스킹 및 JSON 출력 후 후처리 기능으로 안전필터 완화
- 결과: 번역 완료 파일 생성 (형식: 원문=번역문)
- 마스킹 전처리 적용 시 형식: 원문=번역문+마스킹
- 마스킹 전처리+후처리 적용 시 형식: 원문=번역문+마스킹해제(용어집 뜻으로 복원)

[STEP 3] 적용 파일 생성
- 번역된 내용을 원본 에셋 형식에 맞춰 재구성
- 생성된 파일을 UABEA 등을 이용해 게임에 다시 삽입하십시오.
- 스마트 모드는 번역된 내용을 게임 데이터에 적용할 때, 파일 형식에 맞춰 포맷팅을 교정해주는 기능
  1. 텍스트파일 바이너리 헤더 보호
  2. 특수문자 처리: 엔터키(줄바꿈)나 공백 문자를 게임 엔진이 인식할 수 있는 코드로 자동 변환
- 스마트 저장은 번역된 내용이 있는 파일만 저장하는 기능
  1. 번역 DB(번역문)와 매칭되는 문장이 하나도 없는 파일은 저장하지 않음
- UI 등에 있는 짧은영어도 번역하고 싶을때 고급설정 내 영문 보호모드 체크

[문제 해결]
- AI 번역이 멈춘 경우: API 사용량 한도를 확인하거나 '고급 설정'의 Delay를 늘려보세요.
- 영문 보호모드는 연산량이 매우많아 응답없음이 뜹니다. 켜두고 몇분 딴짓하시면 됩니다.
- 영문 보호모드는 일본어, 일본어+영어 유형만 있을 땐 꺼두시는걸 추천드립니다.
"""
        help_textbox.insert("1.0", guide_text)
        help_textbox.configure(state="disabled")

    # --- 6. 정보 탭 ---
    def setup_page_info(self, parent):
        tabview = ctk.CTkTabview(parent)
        tabview.pack(fill="both", expand=True, padx=20, pady=10)
        
        tab_info = tabview.add("프로그램 정보") # 탭 이름 변경
        tab_legal = tabview.add("라이선스 및 면책")
        
        # TAB 1: 정보
        # 중앙 정렬을 위한 컨테이너
        center_frame = ctk.CTkFrame(tab_info, fg_color="transparent")
        center_frame.pack(expand=True, fill="both", padx=20, pady=20)
        center_frame.grid_rowconfigure(0, weight=1)
        center_frame.grid_rowconfigure(4, weight=1)
        center_frame.grid_columnconfigure(0, weight=1)

        # 1. 로고 및 타이틀 영역 (상단 배치)
        info_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        info_frame.grid(row=1, column=0, pady=20)
        
        ctk.CTkLabel(info_frame, text="Game Translator Pro", font=("Arial", 30, "bold")).pack()
        ctk.CTkLabel(info_frame, text="Version: 1.11", text_color="gray", font=("Arial", 14)).pack(pady=5)
        ctk.CTkLabel(info_frame, text="Developed by anysong", font=("Arial", 12)).pack(pady=(0, 20))
        
        # 2. 링크 버튼
        def open_link(url):
            import webbrowser
            webbrowser.open(url)

        btn_github = ctk.CTkButton(info_frame, text="GitHub 프로젝트 방문", 
                                 fg_color="#24292e", hover_color="#1b1f23",
                                 width=200, height=40,
                                 command=lambda: open_link("https://github.com/"))
        btn_github.pack(pady=10)

        # 3. 유틸리티 (배포 준비)
        # 하단에 자연스럽게 위치하도록 설정
        util_frame = ctk.CTkFrame(center_frame, fg_color="transparent")
        util_frame.grid(row=3, column=0, pady=40, sticky="s")
        
        # 구분선 느낌의 라벨
        ctk.CTkLabel(util_frame, text="― 배포 관리 유틸리티 ―", text_color="gray70", font=("Arial", 11)).pack(pady=(0, 10))
        
        ctk.CTkButton(util_frame, text="📄 README.txt 생성하기", 
                      command=self.generate_readme_file, 
                      fg_color="#34495E", hover_color="#2C3E50", 
                      width=200, height=35).pack()

        # TAB 2: 라이선스
        license_text = """
[저작권 고지 (Copyright)]
- 본 프로그램의 모든 권리는 저작권자(anysong)에게 있습니다.
- Copyright © 2025 anysong. All rights reserved.
- 이 프로그램은 CC BY-NC-ND 4.0 라이선스를 따릅니다.
- 비영리 목적의 개인 사용만 가능하며, 상업적 이용 및 수정 재배포를 금지합니다.

[면책 조항 (Disclaimer)]
- 본 프로그램은 데이터 가공 보조 도구로, 게임 바이너리를 직접 수정하지 않습니다.
- 사용자는 외부 툴(UABEA 등)을 통해 추출된 데이터를 준비해야 합니다.
- 소프트웨어 사용으로 인한 모든 기술적/법적 책임은 사용자 본인에게 있습니다.
- 게임사 가이드라인 및 이용약관(EULA) 위반 여부를 반드시 확인하십시오.
- AI 번역 시 발생하는 API 비용은 사용자 부담입니다.
"""

        textbox = ctk.CTkTextbox(tab_legal, font=("Malgun Gothic", 12))
        textbox.pack(fill="both", expand=True, padx=10, pady=10)
        textbox.insert("1.0", license_text)
        textbox.configure(state="disabled")

    # ================================================================
    # [UI Part 4] 하단 로그 패널 (Global)
    # ================================================================
    def setup_log_panel(self):
        # [FIX 3] 프로그레스바와 파일명 표시줄 분리
        # 우측 하단 고정 프레임
        self.log_frame = ctk.CTkFrame(self, height=300, corner_radius=0)
        self.log_frame.grid(row=1, column=1, sticky="nsew") 
        
        # [ROW 1] 진행률 바 + % 숫자
        row_progress = ctk.CTkFrame(self.log_frame, fg_color="transparent", height=20)
        row_progress.pack(fill="x", padx=10, pady=(10, 5))
        
        self.lbl_percent = ctk.CTkLabel(row_progress, text="0%", width=50, font=("Arial", 13, "bold"))
        self.lbl_percent.pack(side="right")
        
        self.progress_bar = ctk.CTkProgressBar(row_progress, height=10)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.progress_bar.set(0)

        # [ROW 2] 현재 파일 상태 (프로그레스바 바로 밑에 배치)
        self.lbl_status = ctk.CTkLabel(self.log_frame, text="Ready", anchor="w", font=("Arial", 12), text_color="gray70")
        self.lbl_status.pack(fill="x", padx=10, pady=(0, 5))

        # [ROW 3] 상세 로그 박스
        self.log_box = ctk.CTkTextbox(self.log_frame, height=210, font=("Consolas", 12))
        self.log_box.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        self.log_box.configure(state="disabled")

    # ================================================================
    # Helper Functions
    # ================================================================
    def create_path_row(self, parent, label, var, is_folder, desc=""):
        wrapper = ctk.CTkFrame(parent, fg_color="transparent")
        wrapper.pack(fill="x", padx=5, pady=5)
        
        lbl = ctk.CTkLabel(wrapper, text=label, width=140, anchor="w", font=("Arial", 12, "bold"))
        lbl.pack(side="left", anchor="n", pady=5)
        
        right_col = ctk.CTkFrame(wrapper, fg_color="transparent")
        right_col.pack(side="left", fill="x", expand=True)
        
        entry_row = ctk.CTkFrame(right_col, fg_color="transparent")
        entry_row.pack(fill="x")
        
        ctk.CTkEntry(entry_row, textvariable=var).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(entry_row, text="📂", width=40, command=lambda: self.browse_path(var, is_folder)).pack(side="left", padx=5)
        
        def open_explorer():
            path = var.get()
            if not path: return
            if os.path.isfile(path): path = os.path.dirname(path)
            if os.path.exists(path): os.startfile(path)

        ctk.CTkButton(entry_row, text="↗", width=40, fg_color="#555", command=open_explorer).pack(side="left")
        
        if desc:
            ctk.CTkLabel(right_col, text=desc, text_color="gray", font=("Arial", 12)).pack(anchor="w", padx=2)

    def log(self, msg):
        def _log():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"> {msg}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _log)

    def update_progress(self, val, text=None):
        # [FIX 3] 분리된 라벨(Status, Percent)에 각각 업데이트
        def _update():
            safe_val = max(0.0, min(1.0, val))
            self.progress_bar.set(safe_val)
            
            # % 표시는 바 우측에
            percent = int(safe_val * 100)
            self.lbl_percent.configure(text=f"{percent}%")
            
            # 파일명/상태 메시지는 바 하단에
            if text:
                self.lbl_status.configure(text=text)
                
        self.after(0, _update)
        
    def browse_path(self, var, is_folder):
        path = filedialog.askdirectory() if is_folder else filedialog.askopenfilename()
        if path:
            var.set(path)
            self.save_config()

    def toggle_buttons(self, state):
        s = "normal" if state else "disabled"
        if hasattr(self, 'btn_extract'): self.btn_extract.configure(state=s)
        if hasattr(self, 'btn_ai'): self.btn_ai.configure(state=s)
        if hasattr(self, 'btn_apply'): self.btn_apply.configure(state=s)

    def wrap_thread(self, target_func, *args):
        def _worker():
            try:
                target_func(*args)
            except Exception as e:
                self.log(f"!! Error: {e}")
            finally:
                self.after(0, lambda: self.toggle_buttons(True))
        self.toggle_buttons(False)
        threading.Thread(target=_worker, daemon=True).start()

    # ================================================================
    # Event Handlers (Logic 연결)
    # ================================================================
    def run_extract(self):
        save_path = filedialog.asksaveasfilename(
            title="저장할 파일명 설정", defaultextension=".txt", initialdir=self.path_out.get(),
            initialfile="_EXTRACTED.txt"
        )
        if not save_path: return
        self.update_progress(0, "추출 시작 중...")
        options = {'group_brackets': self.opt_group_brackets.get(), 'extract_masking': self.opt_extract_masking.get(), 'glossary_path': self.path_glossary.get()}
        self.wrap_thread(logic.process_extract, self.path_src.get(), save_path, options, self.log, self.update_progress)

    def run_ai_translate(self):
        target_input = self.path_ai_input.get().strip() or self.path_src.get().strip()
        if not target_input: return self.log("!! 대상 파일/폴더를 선택하세요.")
        
        if os.path.isfile(target_input):
            out_target = filedialog.asksaveasfilename(title="저장", defaultextension=".txt", initialdir=self.path_out.get())
        else:
            out_target = filedialog.askdirectory(title="저장 폴더", initialdir=self.path_out.get())
        if not out_target: return

        self.update_progress(0, "AI 번역 준비 중...")
        custom_prompt = self.txt_prompt.get("1.0", "end-1c") if hasattr(self, 'txt_prompt') else logic_ai.DEFAULT_PROMPT
        
        options = {
            'provider': self.ai_provider.get(), 'api_key': self.ai_api_key.get(), 'model': self.ai_model.get(),
            'glossary_path': self.path_glossary.get(), 'system_prompt': custom_prompt,
            'chunk_size': self.ai_chunk_size.get(), 'temperature': self.ai_temperature.get(),
            'force_json': self.ai_force_json.get(), 'request_delay': self.ai_request_delay.get(),
            'auto_restore': self.ai_auto_restore.get(), 'auto_mask': self.ai_auto_mask.get()
        }
        self.wrap_thread(logic_ai.process_ai_translation, target_input, out_target, options, self.log, self.update_progress)

    def run_translate(self):
        target_out_dir = filedialog.askdirectory(title="최종 적용 폴더", initialdir=self.path_out.get())
        if not target_out_dir: return
        
        self.update_progress(0, "게임 적용 준비 중...")
        
        options = {
            'smart_mode': self.opt_smart_mode.get(), # 마스터 스위치
            'smart_save': self.opt_smart_save.get(),
            
            # [신규] 세부 옵션 전달
            'smart_header': self.opt_smart_header.get(),
#            'smart_json': self.opt_smart_json.get(),
            'smart_special': self.opt_smart_special.get(),
            'safe_english': self.opt_safe_english.get(),
            
            'newline_key': self.key_newline.get(), 'space_key': self.key_space.get(),
            'tag_pattern': self.tag_custom_pattern.get(), 'db_format': self.db_format.get(),
            'newline_val': self.val_newline.get(), 'space_val': self.val_space.get()
        }
        self.wrap_thread(logic.process_translate, self.path_src.get(), target_out_dir, self.path_db.get(), options, self.log, self.update_progress)

    def run_cost_estimation(self):
        # [수정] self.path_ai_input(선택된 대상)을 가져옴
        target_path = self.path_ai_input.get().strip()
        
        if not target_path:
            self.log("!! [오류] 비용 산출 대상을 찾을 수 없습니다.")
            self.log(">> 위의 '계산 대상' 칸에서 파일이나 폴더를 선택해주세요.")
            return
            
        if not os.path.exists(target_path):
            self.log(f"!! [오류] 경로가 존재하지 않습니다: {target_path}")
            return
        
        self.log(f">> 비용 산출 시작: {os.path.basename(target_path)}")
        
        # [수정] logic_ai에 넘기는 첫 번째 인자를 src_dir가 아닌 target_path로 변경
        self.wrap_thread(
            logic_ai.process_cost_estimation, 
            target_path, 
            self.ai_provider.get(), 
            self.ai_model.get(), 
            self.log
        )

    def update_price_data(self):
        def _update():
            self.log(">> 가격 정보 갱신 중...")
            logic_ai.pricing_engine.fetch_community_data()
            logic_ai.pricing_engine._update_global_models()
            self.after(0, self.refresh_model_list)
            self.log(">> 완료.")
        threading.Thread(target=_update, daemon=True).start()

    def refresh_model_list(self, init=False):
        current_provider = self.ai_provider.get()
        new_models = logic_ai.PROVIDER_MODELS.get(current_provider, [])
        if hasattr(self, 'cbo_model'):
            self.cbo_model.configure(values=new_models)
            if init and new_models: self.ai_model.set(new_models[0])

    def on_provider_change(self, choice):
        self.refresh_model_list()

    def update_tag_ui_state(self, choice):
        if choice == "사용자지정(Regex)":
            self.entry_tag_custom.configure(state="normal")
        else:
            self.entry_tag_custom.configure(state="disabled")

    def reset_to_defaults(self):
        if not messagebox.askyesno("초기화", "고급 설정을 초기화하시겠습니까?"): return
        self.ai_chunk_size.set(15)
        self.ai_temperature.set(0.1)
        self.ai_force_json.set(True)
        if hasattr(self, 'txt_prompt'):
            self.txt_prompt.delete("1.0", "end")
            self.txt_prompt.insert("1.0", DEFAULT_PROMPT)
        self.save_config()
        self.log(">> 설정이 초기화되었습니다.")

    def load_config(self):
        config = configparser.ConfigParser()
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE, encoding='utf-8')
            if 'PATH' in config:
                self.path_src.set(config['PATH'].get('src', ''))
                self.path_out.set(config['PATH'].get('out', ''))
                self.path_db.set(config['PATH'].get('db', ''))
                self.path_glossary.set(config['PATH'].get('glossary', ''))
            if 'AI' in config:
                self.ai_provider.set(config['AI'].get('provider', 'OPENAI'))
                self.ai_api_key.set(config['AI'].get('api_key', ''))

    def save_config(self):
        config = configparser.ConfigParser()
        config['PATH'] = {'src': self.path_src.get(), 'out': self.path_out.get(), 'db': self.path_db.get(), 'glossary': self.path_glossary.get()}
        p_text = self.txt_prompt.get("1.0", "end-1c") if hasattr(self, 'txt_prompt') else DEFAULT_PROMPT
        config['AI'] = {
            'provider': self.ai_provider.get(), 'api_key': self.ai_api_key.get(), 'model': self.ai_model.get(),
            'prompt': p_text.replace('\n', '\\n')
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f: config.write(f)
    
    def generate_readme_file(self):
        content = """===========================================================
 [Game Translator Pro] - Game Translation Asset Injector
===========================================================

# 🎮 Game Translator Pro

**Game Translator Pro**는 Unity 게임 및 텍스트 기반 게임 자산을 위한 **AI 기반 자동 번역 도구**입니다.
Python과 CustomTkinter로 제작되었으며, 텍스트 추출부터 AI 번역, 게임 내 적용까지의 워크플로우를 자동화하여 번역가와 모더의 작업을 돕습니다.

## ✨ 주요 기능 (Key Features)

* **🛠️ 스마트 텍스트 추출 (Smart Extraction)**
    * Unity 에셋 덤프(`UABEA` 등) 파일에서 `m_Text`, `#speaker` 등 불필요한 코드를 제거하고 순수 대사만 추출합니다.
    * 일본어, 영어 등 유효한 텍스트가 있는 라인만 자동으로 선별합니다.

* **🤖 멀티 AI 모델 지원**
    * **OpenAI** (GPT-4o, GPT-4-Turbo 등)
    * **Google** (Gemini 2.5 Pro/Flash)
    * **Anthropic** (Claude 3.5 Sonnet)
    * **DeepL** API 지원
    * 실시간 가격 및 모델 정보를 불러와 **예상 번역 비용**을 미리 계산해줍니다.

* **🛡️ 용어집 및 마스킹 (Glossary & Masking)**
    * 고유명사 보호 및 안전필터 회피를 위한 **마스킹 시스템** (`__MASK_001__`) 탑재.
    * 3단 용어집 지원 (`원문, 의미/힌트, 번역문`)으로 AI에게 문맥 힌트를 제공하여 번역 품질을 극대화합니다.
    * CSV, TXT 형식의 용어집을 지원합니다.

* **⚡ 사용자 편의성**
    * **CustomTkinter** 기반의 깔끔한 Dark/Light 모드 GUI.
    * 대용량 파일 처리를 위한 멀티스레딩 지원.
    * 작업 진행 상황 실시간 로그 및 프로그레스 바 표시.

1. 저작권 고지 (Copyright)
-----------------------------------------------------------
본 프로그램의 모든 권리는 저작권자(anysong)에게 있습니다.
Copyright © 2025 anysong. All rights reserved.
이 프로그램은 CC BY-NC-ND 4.0 라이선스를 따릅니다.
비영리 목적의 개인 사용만 가능하며, 상업적 이용 및 수정 재배포를 금지합니다.

2. 면책 조항 (Disclaimer)]
- 본 프로그램은 데이터 가공 보조 도구로, 게임 바이너리를 직접 수정하지 않습니다.
- 사용자는 외부 툴(UABEA 등)을 통해 추출된 데이터를 준비해야 합니다.
- 소프트웨어 사용으로 인한 모든 기술적/법적 책임은 사용자 본인에게 있습니다.
- 게임사 가이드라인 및 이용약관(EULA) 위반 여부를 반드시 확인하십시오.
- AI 번역 시 발생하는 API 비용은 사용자 부담입니다.
===========================================================
"""
        try:
            path = os.path.join(BASE_DIR, "README.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("완료", f"README.txt 파일이 생성되었습니다:\n{path}")
            os.startfile(path)
        except Exception as e:
            messagebox.showerror("오류", f"파일 생성 실패: {e}")

    def generate_sample_glossary(self):
        
        # CSV 샘플
        sample_csv = (
            "일본어 원문,의미/설명,한국어 추천 번역\n"
            "ハァハァ,거친 숨소리,하아하아\n"
            "ドキッ,심장이 뛰는 소리,두근"
        )
        
        #TXT 샘플
        sample_txt = "일본어 원문,의미/설명,한국어 추천 번역\nハァハァ,거친 숨소리,하아하아"
        
        try:
            # 2종 파일 저장
            paths = {
                "TXT": os.path.join(BASE_DIR, "glossary_sample.txt"),
                "CSV": os.path.join(BASE_DIR, "glossary_sample.csv")
            }
            
            with open(paths["TXT"], "w", encoding="utf-8") as f: f.write(sample_txt)
            with open(paths["CSV"], "w", encoding="utf-8-sig") as f: f.write(sample_csv) # 엑셀 호환용
                
            messagebox.showinfo("완료", "용어집 샘플 2종(TXT, CSV)이 생성되었습니다.")
            os.startfile(BASE_DIR) 
        except Exception as e:
            messagebox.showerror("오류", f"파일 생성 실패: {e}")

if __name__ == "__main__":
    app = TranslatorApp()
    app.mainloop()
