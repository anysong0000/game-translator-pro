# -*- coding: utf-8 -*-
"""
Project: Game Translator Pro
Author: anysong
Copyright: Copyright © 2025 anysong. All rights reserved.
License: CC BY-NC-ND 4.0 (Attribution-NonCommercial-NoDerivs)

Disclaimer: 
This software is provided "as is", without warranty of any kind. 
The user assumes all responsibility for any modifications made to game files.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import threading
import configparser

# 모듈 가져오기 (사용자 기존 모듈 유지)
import logic
import logic_ai 
import utils

# ==========================================
# 설정 및 상수
# ==========================================
WINDOW_TITLE = "Game Translator Pro v1.0"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")

# 기본 프롬프트
DEFAULT_PROMPT = (
    "You are a professional game translator.\n"
    "Output must be a JSON array of objects. Format: [{\"id\": 1, \"trans\": \"Korean text\"}, ...]\n"
    "Do NOT translate tokens like __MASK_XXX__.\n"
    "Translate the 'text' field into natural Korean 'trans'."
)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class TranslatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("1100x800")
        
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
        # 기존 변수 그대로 유지
        self.path_src = tk.StringVar()
        self.path_out = tk.StringVar()
        self.path_db = tk.StringVar()
        self.path_glossary = tk.StringVar()
        self.path_util_db = tk.StringVar()
        self.path_ai_input = tk.StringVar()
        
        self.opt_group_brackets = tk.BooleanVar(value=True)
        self.opt_extract_masking = tk.BooleanVar(value=False)
        
        self.db_format = tk.StringVar(value=".txt")
        self.opt_smart_mode = tk.BooleanVar(value=True)
        self.opt_smart_save = tk.BooleanVar(value=True)
        self.key_newline = tk.StringVar(value="\\n")
        self.key_space = tk.StringVar(value=" ")
        self.val_newline = tk.StringVar(value="[실제 줄바꿈]")
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
        # [FIX 2] 눈뽕 방지: 라이트 모드 배경을 'transparent'(흰색) 대신 부드러운 회색('gray94')으로 설정
        bg_color = ("gray94", "gray17")
        
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

        self.frames["advanced"] = ctk.CTkFrame(self.main_container, fg_color=frame_bg)
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
        card3 = self.create_workflow_card(parent, "STEP 3. 게임 적용", "#27AE60", 2)
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
        self.create_path_row(container, "용어집 (Glossary):", self.path_glossary, is_folder=False, desc="고유명사 번역을 고정할 JSON/TXT 파일")
        
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
        
        btn_box = ctk.CTkFrame(tool_frame, fg_color="transparent")
        btn_box.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkButton(btn_box, text="🔄 가격표 갱신 (Web)", command=self.update_price_data, fg_color="#34495E").pack(side="left", padx=5)
        ctk.CTkButton(btn_box, text="💸 예상 비용 산출 (전체 스캔)", command=self.run_cost_estimation, fg_color="#2980B9").pack(side="left", padx=5)

    # --- 4. 고급 설정 ---
    def setup_page_advanced(self, parent):
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
        
        ctk.CTkLabel(frame_ai, text="System Prompt:", anchor="w").pack(fill="x", padx=10)
        self.txt_prompt = ctk.CTkTextbox(frame_ai, height=100, font=("Consolas", 11))
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

        # 초기화 버튼
        ctk.CTkButton(parent, text="🔄 공장 초기화 (설정 리셋)", fg_color="#C0392B", command=self.reset_to_defaults).pack(pady=20)

        # --- 5. 도움말 탭 ---
    def setup_page_help(self, parent):
        ctk.CTkLabel(parent, text="사용 가이드 (User Guide)", font=("Arial", 20, "bold")).pack(anchor="w", padx=20, pady=20)
        
        help_textbox = ctk.CTkTextbox(parent, font=("Malgun Gothic", 14), height=400)
        help_textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        guide_text = """
[STEP 1] 텍스트 추출
1. '프로젝트 설정' 탭에서 게임의 원본 폴더(Source)를 지정합니다.
2. '추출 시작' 버튼을 누르면 게임 내 텍스트가 txt 파일로 추출됩니다.
3. 팁: '대사 괄호 보호'를 켜면 이름이나 중요 구문을 보호할 수 있습니다.

[STEP 2] AI 번역
1. 추출된 텍스트 파일을 선택합니다.
2. 'AI 설정' 탭에서 API Key가 올바른지 확인하세요.
3. 번역이 시작되면 실시간으로 진행률이 표시됩니다.
4. 비용 절약을 위해 '고급 설정'에서 프롬프트를 최적화할 수 있습니다.

[STEP 3] 게임 적용
1. 번역이 완료된 파일(txt/json)을 선택합니다.
2. '적용 시작'을 누르면 게임 파일에 번역문이 입혀집니다.
3. '스마트 모드'를 켜면 기존 형식을 최대한 유지하며 적용합니다.

[문제 해결]
- 번역이 멈춘 경우: API 사용량 한도를 확인하거나 '고급 설정'의 Delay를 늘려보세요.
- 글자가 깨지는 경우: 게임 폰트가 한글을 지원하는지 확인해야 합니다.
"""
        help_textbox.insert("1.0", guide_text)
        help_textbox.configure(state="disabled")

    # --- 6. 정보 탭 ---
    def setup_page_info(self, parent):
        tabview = ctk.CTkTabview(parent)
        tabview.pack(fill="both", expand=True, padx=20, pady=10)
        
        tab_info = tabview.add("정보 및 후원")
        tab_legal = tabview.add("라이선스 및 면책")
        
        # TAB 1: 정보 및 후원
        info_frame = ctk.CTkFrame(tab_info, fg_color="transparent")
        info_frame.pack(fill="x", pady=20)
        
        ctk.CTkLabel(info_frame, text="Game Translator Pro", font=("Arial", 30, "bold")).pack()
        ctk.CTkLabel(info_frame, text="Version: 1.0", text_color="gray").pack()
        ctk.CTkLabel(info_frame, text="Developed by anysong", font=("Arial", 12)).pack(pady=10)
        
        # 1. 후원 프레임 테두리
        sponsor_frame = ctk.CTkFrame(tab_info, border_width=2, border_color=("#0064FF", "#3B8ED0"))
        sponsor_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(sponsor_frame, text="💙 프로그램 개발 응원하기", 
                     font=("Arial", 18, "bold"), text_color=("#0064FF", "#3B8ED0")).pack(pady=(20, 10))
        
        sponsor_msg = (
            "후원 시 남겨주신 닉네임과 응원 메시지는 개발자에게 큰 힘이 됩니다!\n"
            "보내주신 후원금은 사리사욕을 위해 소중히 사용하겠습니다."
        )
        ctk.CTkLabel(sponsor_frame, text=sponsor_msg, text_color=("black", "white")).pack(pady=(0, 20))
        
        btn_box = ctk.CTkFrame(sponsor_frame, fg_color="transparent")
        btn_box.pack(pady=(0, 20))
        
        def open_link(url):
            import webbrowser
            webbrowser.open(url)

        # 투네이션 버튼 (닉네임 확인 가능)
        ctk.CTkButton(btn_box, text="투네이션으로 후원 (닉네임 가능)", 
                      fg_color="#0064FF", hover_color="#0052D1",
                      command=lambda: open_link("https://toon.at/donate/anysong0000")).pack(side="left", padx=10)
        
        # 깃허브 버튼 (신뢰도용)
        ctk.CTkButton(btn_box, text="GitHub 프로젝트 방문", fg_color="#24292e", 
                      command=lambda: open_link("https://github.com/")).pack(side="left", padx=10)

        # 2. 하단 안내
        notice_lbl = ctk.CTkLabel(tab_info, text="* 후원 후 알려주시면 다음 버전 '도움주신 분들'에 기록해 드립니다.", 
                                  font=("Arial", 11), text_color="gray")
        notice_lbl.pack(pady=5)

        # 3. 유틸리티
        util_frame = ctk.CTkFrame(tab_info, fg_color="transparent")
        util_frame.pack(fill="x", padx=20, pady=20, side="bottom")
        
        ctk.CTkLabel(util_frame, text="배포 준비:", font=("Arial", 12, "bold")).pack(side="left")
        ctk.CTkButton(util_frame, text="📄 README.txt 생성하기", 
                      command=self.generate_readme_file, fg_color="#34495E", width=150).pack(side="left", padx=10)

        # TAB 2: 라이선스
        license_text = """
[저작권 고지 (Copyright)]
Copyright © 2025 anysong. All rights reserved.
이 프로그램은 CC BY-NC-ND 4.0 (저작자 표시-비영리-변경 금지) 라이선스를 따릅니다.
- 개인적인 용도로만 사용 가능하며, 상업적 이용 및 무단 재배포를 금지합니다.

[면책 조항 (Disclaimer)]
1. 본 프로그램은 사용자가 보유한 게임 파일의 텍스트 데이터를 추출하고 수정(Injection)하는 도구입니다.
2. 본 프로그램을 사용하여 발생하는 게임 서비스 이용 제한(밴), 세이브 파일 손상, 게임사의 서비스 이용약관(EULA) 위반 등 모든 기술적/법적 책임은 사용자 본인에게 있습니다.
3. 제작자는 본 프로그램을 사용하여 발생하는 어떠한 손해(데이터 유실, 계정 정지 등)에 대해서도 책임을 지지 않습니다.
4. 사용자는 반드시 원본 파일을 백업한 후 프로그램을 사용하시기 바랍니다.

[소스 코드 공개]
본 프로그램의 소스 코드는 추후 GitHub를 통해 공개될 예정입니다.
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
        self.log_frame = ctk.CTkFrame(self, height=180, corner_radius=0)
        self.log_frame.grid(row=1, column=1, sticky="nsew") 
        
        # [ROW 1] 진행률 바 + % 숫자
        row_progress = ctk.CTkFrame(self.log_frame, fg_color="transparent", height=20)
        row_progress.pack(fill="x", padx=10, pady=(10, 5))
        
        self.lbl_percent = ctk.CTkLabel(row_progress, text="0%", width=50, font=("Arial", 12, "bold"))
        self.lbl_percent.pack(side="right")
        
        self.progress_bar = ctk.CTkProgressBar(row_progress, height=10)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.progress_bar.set(0)

        # [ROW 2] 현재 파일 상태 (프로그레스바 바로 밑에 배치)
        self.lbl_status = ctk.CTkLabel(self.log_frame, text="Ready", anchor="w", font=("Arial", 11), text_color="gray70")
        self.lbl_status.pack(fill="x", padx=10, pady=(0, 5))

        # [ROW 3] 상세 로그 박스
        self.log_box = ctk.CTkTextbox(self.log_frame, height=100, font=("Consolas", 10))
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
            ctk.CTkLabel(right_col, text=desc, text_color="gray", font=("Arial", 10)).pack(anchor="w", padx=2)

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
            'force_json': self.ai_force_json.get(), 'request_delay': self.ai_request_delay.get()
        }
        self.wrap_thread(logic_ai.process_ai_translation, target_input, out_target, options, self.log, self.update_progress)

    def run_translate(self):
        target_out_dir = filedialog.askdirectory(title="최종 적용 폴더", initialdir=self.path_out.get())
        if not target_out_dir: return
        
        self.update_progress(0, "게임 적용 준비 중...")
        options = {
            'smart_mode': self.opt_smart_mode.get(), 'smart_save': self.opt_smart_save.get(),
            'newline_key': self.key_newline.get(), 'space_key': self.key_space.get(),
            'tag_pattern': self.tag_custom_pattern.get(), 'db_format': self.db_format.get(),
            'newline_val': self.val_newline.get(), 'space_val': self.val_space.get()
        }
        self.wrap_thread(logic.process_translate, self.path_src.get(), target_out_dir, self.path_db.get(), options, self.log, self.update_progress)

    def run_cost_estimation(self):
        self.wrap_thread(logic_ai.process_cost_estimation, self.path_src.get(), self.ai_provider.get(), self.ai_model.get(), self.log)

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

1. 저작권 고지 (Copyright)
-----------------------------------------------------------
본 프로그램의 모든 권리는 저작권자(anysong)에게 있습니다.
Copyright © 2025 anysong. All rights reserved.

본 프로그램은 Creative Commons (CC BY-NC-ND 4.0) 라이선스를 따릅니다.
- 저작자 표시: 원저작자를 명시해야 합니다.
- 비영리: 본 프로그램을 유료로 판매하거나 상업적 목적으로 이용할 수 없습니다.
- 변경 금지: 본 프로그램을 수정, 변형하여 재배포하는 것을 금지합니다.

2. 면책 조항 (Disclaimer)
-----------------------------------------------------------
- 본 프로그램은 게임 파일의 데이터를 수정(Injection)하는 기능을 포함하고 있습니다.
- 프로그램 사용으로 인해 발생하는 게임 서비스 이용 제한(밴), 세이브 파일 손상, 
  모든 기술적/법적 책임은 사용자 본인에게 있습니다.
- 사용자는 반드시 원본 파일을 백업한 후 프로그램을 사용하시기 바랍니다.

3. 후원 및 문의
-----------------------------------------------------------
개발자의 지속적인 업데이트를 지원하고 싶으시다면 아래 링크를 확인해주세요.
(프로그램 내 '정보' 탭에서 후원 버튼을 클릭할 수 있습니다.)
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

if __name__ == "__main__":
    app = TranslatorApp()
    app.mainloop()