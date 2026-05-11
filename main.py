import re
import pyperclip
import threading
import platform
import keyboard
from thefuzz import fuzz
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Tree, DataTable, Input, Button, Label
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.binding import Binding
from textual.screen import ModalScreen
from textual import on, events
from database import DatabaseManager

class CategoryTree(Tree):
    """사이드바 전용 카테고리 트리 (Enter 입력 시 펼침 토글 방지)"""
    
    BINDINGS = [
        Binding("enter", "custom_select", "선택 및 이동", show=False),
        # Space는 Textual 기본 설정(toggle_node)으로 자연스럽게 접기/펼치기가 작동합니다.
    ]

    def action_custom_select(self) -> None:
        """Enter 키를 눌렀을 때 토글을 방지하고 선택 이벤트(NodeSelected)만 발생시킵니다."""
        if self.cursor_node is not None:
            self.post_message(self.NodeSelected(self.cursor_node))

def bring_to_front():
    """OS별 터미널 창 최상단 활성화 (글로벌 단축키 트리거 시 호출)"""
    system = platform.system()
    if system == "Windows":
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 9) # SW_RESTORE (9)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    elif system == "Darwin":
        import subprocess
        subprocess.run(["osascript", "-e", 'tell application "Terminal" to activate'], check=False)
    elif system == "Linux":
        import subprocess
        try:
            subprocess.run(["wmctrl", "-a", "Command-Flow"], check=False)
        except Exception:
            pass

class VariableModal(ModalScreen[dict]):
    """동적 변수 입력을 받는 모달 창"""
    
    CSS = """
    VariableModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #modal-container {
        width: 50;
        height: auto;
        background: $surface;
        border: tall $primary;
        padding: 1 2;
    }
    .var-input {
        margin-bottom: 1;
    }
    #button-container {
        align: right middle;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "취소")]

    def __init__(self, variables: list[str]):
        super().__init__()
        self.variables = variables

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-container"):
            yield Label("변수 값을 입력하세요:")
            for var in self.variables:
                yield Input(placeholder=f"{var}", id=f"input-{var}", classes="var-input")
            with Horizontal(id="button-container"):
                yield Button("확인", variant="primary", id="btn-submit")
                yield Button("취소", variant="error", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-submit":
            self._submit()
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    @on(Input.Submitted)
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        result = {}
        for var in self.variables:
            val = self.query_one(f"#input-{var}", Input).value
            result[var] = val
        self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss(None)

class AddCommandModal(ModalScreen[dict]):
    """새로운 명령어를 추가하는 모달 창"""

    CSS = """
    AddCommandModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #add-modal-container {
        width: 60;
        height: auto;
        background: $surface;
        border: tall $primary;
        padding: 1 2;
    }
    .add-input {
        margin-bottom: 1;
    }
    #add-button-container {
        align: right middle;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "취소")]

    def compose(self) -> ComposeResult:
        with Vertical(id="add-modal-container"):
            yield Label("새 명령어 추가")
            yield Input(placeholder="대분류 (예: git) *필수", id="input-large_category", classes="add-input")
            yield Input(placeholder="중분류 (예: branch)", id="input-medium_category", classes="add-input")
            yield Input(placeholder="소분류 (예: create)", id="input-small_category", classes="add-input")
            yield Input(placeholder="명령어 (예: git checkout -b {{branch}}) *필수", id="input-command", classes="add-input")
            yield Input(placeholder="설명", id="input-description", classes="add-input")
            yield Input(placeholder="태그 (쉼표로 구분)", id="input-tags", classes="add-input")
            with Horizontal(id="add-button-container"):
                yield Button("추가", variant="primary", id="btn-add-submit")
                yield Button("취소", variant="error", id="btn-add-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-add-submit":
            result = {
                "large_category": self.query_one("#input-large_category", Input).value.strip(),
                "medium_category": self.query_one("#input-medium_category", Input).value.strip(),
                "small_category": self.query_one("#input-small_category", Input).value.strip(),
                "command": self.query_one("#input-command", Input).value.strip(),
                "description": self.query_one("#input-description", Input).value.strip(),
                "tags": self.query_one("#input-tags", Input).value.strip(),
            }
            if not result["large_category"] or not result["command"]:
                self.app.notify("대분류와 명령어는 필수 입력 항목입니다.", severity="warning")
                return
            self.dismiss(result)
        elif event.button.id == "btn-add-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

class SeparatorModal(ModalScreen[str]):
    """다중 복사 시 사용할 구분자 입력 모달 창"""

    CSS = """
    SeparatorModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #sep-modal-container {
        width: 50;
        height: auto;
        background: $surface;
        border: tall $primary;
        padding: 1 2;
    }
    .sep-btn {
        margin-top: 1;
        margin-right: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "취소")]

    def compose(self) -> ComposeResult:
        with Vertical(id="sep-modal-container"):
            yield Label("다중 복사 구분자를 입력하세요 (기본값: 줄바꿈)")
            yield Input(placeholder="예: \\n, ;, |, 등", id="input-sep", value="\\n")
            with Horizontal():
                yield Button("확인", variant="primary", id="btn-sep-submit", classes="sep-btn")
                yield Button("취소", variant="error", id="btn-sep-cancel", classes="sep-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-sep-submit":
            self._submit()
        elif event.button.id == "btn-sep-cancel":
            self.dismiss(None)

    @on(Input.Submitted, "#input-sep")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        val = self.query_one("#input-sep", Input).value
        val = val.replace("\\n", "\n") # 사용자가 \n을 문자로 입력했을 때 실제 개행문자로 변환
        self.dismiss(val)

    def action_cancel(self) -> None:
        self.dismiss(None)

class ConfirmDeleteModal(ModalScreen[bool]):
    """명령어 다중 삭제 확인 모달 창"""

    CSS = """
    ConfirmDeleteModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #confirm-modal-container {
        width: 50;
        height: auto;
        background: $surface;
        border: tall $error;
        padding: 1 2;
    }
    #confirm-button-container {
        align: right middle;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "취소")]

    def __init__(self, count: int):
        super().__init__()
        self.count = count

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-modal-container"):
            yield Label(f"⚠️ 선택한 {self.count}개의 투플(명령어)을 삭제하시겠습니까?")
            with Horizontal(id="confirm-button-container"):
                yield Button("삭제", variant="error", id="btn-confirm-delete")
                yield Button("취소", variant="primary", id="btn-confirm-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm-delete":
            self.dismiss(True)
        elif event.button.id == "btn-confirm-cancel":
            self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)

class HelpModal(ModalScreen[None]):
    """도움말 및 단축키 안내 모달 창"""

    CSS = """
    HelpModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #help-modal-container {
        width: 75;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: tall $primary;
        padding: 1 2;
    }
    #help-button-container {
        align: right middle;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [Binding("escape", "cancel", "닫기")]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-modal-container"):
            yield Label("[b]📖 Command-Flow 도움말 및 단축키[/b]", classes="text-center")
            yield Label("") # 여백용 빈 라인
            help_text = """[b]🚀 주요 기능[/b]
• [u]자동 복사[/u]: 명령어를 선택(Enter)하면 클립보드에 자동 복사됩니다.
• [u]동적 변수 치환[/u]: 명령어에 '{{변수명}}'이 포함되어 있으면, 
                복사 전 값을 입력받는 창이 뜹니다.
• [u]퍼지 검색[/u]: 오타가 있거나 일부만 입력해도 똑똑하게 검색해 줍니다.
• [u]글로벌 단축키[/u]: 백그라운드 실행 중 'Ctrl + `'를 누르면 언제든 창이 
                최상단으로 호출됩니다.

[b]⌨️ 단축키 안내[/b]
• [b]/[/b] : 검색창 열기/닫기
• [b]a[/b] : 새 명령어 추가
• [b]e[/b] : 명령어 삭제 모드 진입/실행
• [b]h[/b] : 도움말 보기
• [b]q[/b] : 프로그램 종료
• [b]Enter[/b] : 명령어 복사 (단일 복사 / 다중 선택 시 다중 복사)
• [b]Space[/b] : 명령어 다중 선택/해제 (삭제 모드 시: 삭제 항목 선택)
• [b]ESC[/b] : 팝업 닫기, 검색창 닫기, 삭제/다중 선택 취소
• [b]방향키 (←/→)[/b] : 사이드바와 메인 테이블 간 포커스 이동
• [b]Ctrl+`[/b] : 터미널 창을 최상단으로 호출"""
            yield Label(help_text)
            with Horizontal(id="help-button-container"):
                yield Button("닫기", variant="primary", id="btn-help-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-help-close":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

class SearchInput(Input):
    """검색창 전용 Input (슬래시(/) 또는 ESC 입력 시 검색창 닫기)"""
    BINDINGS = [
        Binding("/", "toggle_search", "검색창 닫기"),
        Binding("escape", "toggle_search", "닫기", show=False)
    ]

    def action_toggle_search(self) -> None:
        self.app.action_search()

class CommandFlowApp(App):
    """Command-Flow TUI Application"""

    # 앱 전반에 적용될 기본 CSS 디자인
    CSS = """
    Screen {
        layout: horizontal;
    }

    #sidebar {
        width: 30;
        height: 100%;
        dock: left;
        border-right: solid $primary;
    }

    #main-content {
        width: 1fr;
        height: 100%;
    }

    #search-container {
        dock: top;
        height: 3;
        display: none;
    }
    #search-container.-visible {
        display: block;
    }
    #multi-select-container {
        dock: top;
        height: 3;
        display: none;
        background: $panel;
        padding-left: 2;
        padding-top: 1;
    }
    #multi-select-container.-visible {
        display: block;
    }
    #cmd-table {
        height: 1fr;
    }
    """

    # 하단 Footer에 표시될 단축키 힌트
    BINDINGS = [
        Binding("q", "quit", "종료"),
        Binding("/", "search", "검색"),
        Binding("a", "add", "추가"),
        Binding("e", "manage", "관리(삭제)"),
        Binding("h", "help", "도움말"),
        Binding("space", "toggle_multi_select", "다중 선택"),
    ]

    def __init__(self):
        super().__init__()
        # DB 초기화 및 더미 데이터 준비
        self.db = DatabaseManager()
        self.db.init_db()
        self.db.insert_dummy_data()
        self.current_large_category = None
        self.current_medium_category = None
        self.delete_mode = False
        self.delete_selections = set()
        self.multi_selections = {}

    def compose(self) -> ComposeResult:
        """UI 위젯을 화면에 배치합니다."""
        yield Header(show_clock=True)
        with Horizontal():
            yield CategoryTree("모든 카테고리", id="sidebar")
            with Vertical(id="main-content"):
                with Horizontal(id="search-container"):
                    yield SearchInput(placeholder="명령어, 설명, 태그 검색... (퍼지 검색)", id="search-input")
                with Horizontal(id="multi-select-container"):
                    yield Label("", id="multi-select-label")
                yield DataTable(id="cmd-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        """UI 요소가 마운트될 때 실행되는 초기화 로직"""
        self.title = "Command-Flow"
        
        # 글로벌 단축키(백그라운드 스레드) 등록
        self._start_hotkey_thread()

        # 1. 사이드바 트리 초기화
        self._build_tree()
            
        # 2. 메인 데이터 테이블 컬럼 설정
        table = self.query_one("#cmd-table", DataTable)
        table.add_column("ID", key="id")
        table.add_column("분류", key="category")
        table.add_column("명령어", key="command")
        table.add_column("설명", key="desc")
        table.add_column("태그", key="tags")
        
        # 3. 최초 화면에 모든 명령어 데이터 로드
        self._refresh_current_table()

    def _build_tree(self) -> None:
        """데이터베이스에서 카테고리를 읽어와 사이드바 트리를 재구성합니다."""
        tree = self.query_one("#sidebar", CategoryTree)
        tree.clear()
        tree.root.expand()
        
        tree_data = self.db.get_category_tree()
        for l_cat, m_cats in tree_data.items():
            # 대분류 노드 추가
            l_node = tree.root.add(l_cat, data={"large": l_cat, "medium": None})
            for m_cat in m_cats:
                if m_cat: # 중분류가 존재하는 경우만
                    l_node.add_leaf(m_cat, data={"large": l_cat, "medium": m_cat})

    def _refresh_current_table(self) -> None:
        """현재 카테고리와 검색어를 기준으로 테이블 데이터를 갱신합니다."""
        query = self.query_one("#search-input", Input).value.strip().lower()
        
        all_commands = self.db.get_all_commands()
        target_commands = []
        for cmd in all_commands:
            if self.current_large_category and cmd['large_category'] != self.current_large_category:
                continue
            if self.current_medium_category and cmd['medium_category'] != self.current_medium_category:
                continue
            target_commands.append(cmd)
        
        if not query:
            self._populate_table(target_commands)
            return
            
        results = []
        for cmd in target_commands:
            target_text = f"{cmd['command']} {cmd['description']} {cmd['tags']}".lower()
            score = fuzz.partial_ratio(query, target_text)
            if score > 40:
                results.append((score, cmd))
        results.sort(key=lambda x: x[0], reverse=True)
        self._populate_table([item[1] for item in results])

    def _populate_table(self, commands: list):
        """테이블 내용을 지우고 새로운 데이터로 채우는 헬퍼 메서드"""
        table = self.query_one("#cmd-table", DataTable)
        table.clear()
        for cmd in commands:
            cmd_id = cmd['id']
            if getattr(self, "delete_mode", False):
                id_display = f"[{'x' if cmd_id in self.delete_selections else ' '}] {cmd_id}"
            elif getattr(self, "multi_selections", None) and cmd_id in self.multi_selections:
                id_display = f"[✓] {cmd_id}"
            else:
                id_display = str(cmd_id)
                
            cat_display = f"{cmd['large_category']} > {cmd['medium_category']}"
            if cmd.get('small_category'):
                cat_display += f" > {cmd['small_category']}"

            table.add_row(
                id_display,
                cat_display,
                cmd['command'],
                cmd['description'],
                cmd['tags'],
                key=str(cmd_id)
            )

    def action_add(self) -> None:
        """'a' 키 입력 시 새 명령어 추가 모달을 띄웁니다."""
        def check_add_result(result: dict | None) -> None:
            if result is not None:
                self.db.insert_command(**result)
                self.notify("새 명령어가 성공적으로 추가되었습니다!", title="추가 완료")
                
                # 트리 재구성
                self._build_tree()
                
                # 테이블 화면 갱신
                self._refresh_current_table()
                    
        self.push_screen(AddCommandModal(), check_add_result)

    def action_manage(self) -> None:
        """'e' 키 입력 시 관리(삭제) 모드를 토글합니다."""
        if not self.delete_mode:
            self.delete_mode = True
            self.delete_selections = set()
            self.multi_selections.clear()
            self._update_multi_select_ui()
            self.notify("삭제 모드: Space로 삭제할 항목 선택 후, e를 다시 누르세요. (ESC: 취소)", timeout=5)
            self._refresh_current_table()
            self.query_one("#cmd-table").focus()
        else:
            if not self.delete_selections:
                self.notify("선택된 명령어가 없습니다.", severity="warning")
                return
            
            def check_manage_result(confirm: bool | None) -> None:
                if confirm:
                    success_count = 0
                    for cmd_id in self.delete_selections:
                        if self.db.delete_command(cmd_id):
                            success_count += 1
                    
                    self.notify(f"{success_count}개의 명령어가 성공적으로 삭제되었습니다.", title="삭제 완료")
                    self.delete_mode = False
                    self.delete_selections.clear()
                    self._update_multi_select_ui()
                    
                    # 트리 재구성
                    self._build_tree()
                        
                    self._refresh_current_table()

            self.push_screen(ConfirmDeleteModal(len(self.delete_selections)), check_manage_result)

    def action_search(self) -> None:
        """'/' 키 입력 시 검색창을 토글하고 포커스를 이동합니다."""
        search_container = self.query_one("#search-container")
        search_input = self.query_one("#search-input", Input)
        
        if search_container.has_class("-visible"):
            search_container.remove_class("-visible")
            search_input.value = "" # 검색어 초기화
            self.query_one("#cmd-table").focus()
            
            self._refresh_current_table()
        else:
            search_container.add_class("-visible")
            search_input.focus()

    def action_help(self) -> None:
        """'h' 키 입력 시 도움말 모달을 띄웁니다."""
        self.push_screen(HelpModal())

    def action_toggle_multi_select(self) -> None:
        """Space 입력 시 다중 복사 및 삭제를 위한 명령어 선택 토글"""
        table = self.query_one("#cmd-table", DataTable)
        if not table.has_focus or not table.row_count:
            return
        
        try:
            cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
            row_key = cell_key[0] if isinstance(cell_key, tuple) else cell_key.row_key
            cmd_id = int(row_key.value)
            
            if getattr(self, "delete_mode", False):
                if cmd_id in self.delete_selections:
                    self.delete_selections.remove(cmd_id)
                    table.update_cell(row_key, "id", f"[ ] {cmd_id}")
                else:
                    self.delete_selections.add(cmd_id)
                    table.update_cell(row_key, "id", f"[x] {cmd_id}")
            else:
                row_data = table.get_row(row_key)
                command_str = row_data[2] # 명령어 컬럼
                if cmd_id in self.multi_selections:
                    del self.multi_selections[cmd_id]
                    table.update_cell(row_key, "id", str(cmd_id))
                else:
                    self.multi_selections[cmd_id] = command_str
                    table.update_cell(row_key, "id", f"[✓] {cmd_id}")
                
            self._update_multi_select_ui()
        except Exception:
            pass

    def _update_multi_select_ui(self) -> None:
        container = self.query_one("#multi-select-container")
        label = self.query_one("#multi-select-label", Label)
        
        if getattr(self, "delete_mode", False):
            if self.delete_selections:
                container.add_class("-visible")
                ids = ", ".join(str(k) for k in self.delete_selections)
                label.update(f"🗑️ [b]삭제 대기 ID:[/b] {ids}  (삭제 실행: 'e' 키)")
            else:
                container.remove_class("-visible")
        else:
            if self.multi_selections:
                container.add_class("-visible")
                ids = ", ".join(str(k) for k in self.multi_selections.keys())
                label.update(f"🛒 [b]선택된 ID:[/b] {ids}  (다중 복사 실행: 'Enter' 키)")
            else:
                container.remove_class("-visible")

    def _execute_multi_copy(self) -> None:
        """다중 선택된 명령어 복사 진행"""
        if not self.multi_selections:
            return
        
        def check_separator(sep: str | None) -> None:
            if sep is not None:
                combined_cmds = sep.join(self.multi_selections.values())
                # 다중 복사에도 동적 변수가 포함되어 있다면 한 번에 입력받음
                self._handle_copy_with_variables(combined_cmds)
                
                self.multi_selections.clear()
                self._update_multi_select_ui()
                self._refresh_current_table()

        self.push_screen(SeparatorModal(), check_separator)

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        """검색어 입력 시 thefuzz를 이용한 퍼지 검색 수행"""
        self._refresh_current_table()

    def _start_hotkey_thread(self):
        """백그라운드에서 전역 단축키 이벤트를 수신하는 스레드"""
        def hotkey_listener():
            # Ctrl+` 입력 시 터미널 창을 최상단으로 끌어올림
            keyboard.add_hotkey('ctrl+`', bring_to_front)
            keyboard.wait()
            
        t = threading.Thread(target=hotkey_listener, daemon=True)
        t.start()

    @on(Tree.NodeSelected)
    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """사이드바 트리 노드 선택 시 카테고리 필터링"""
        node_data = event.node.data
        if node_data is None: # 루트 노드 ("모든 카테고리")
            self.current_large_category = None
            self.current_medium_category = None
        else:
            self.current_large_category = node_data.get("large")
            self.current_medium_category = node_data.get("medium")
        
        # 카테고리 변경 시 기존 검색어가 있다면 초기화
        search_input = self.query_one("#search-input", Input)
        if search_input.value:
            search_input.value = ""
            
        self._refresh_current_table()
            
        # 카테고리 선택 후 메인 테이블(DataTable)로 자동 포커스 이동
        self.query_one("#cmd-table").focus()

    def on_key(self, event: events.Key) -> None:
        """ESC 키 동작 및 방향키 포커스 이동"""
        if event.key == "escape":
            if getattr(self, "delete_mode", False):
                self.delete_mode = False
                self.delete_selections.clear()
                self._update_multi_select_ui()
                self.notify("삭제 모드가 취소되었습니다.")
                self._refresh_current_table()
                return
            elif getattr(self, "multi_selections", False):
                self.multi_selections.clear()
                self._update_multi_select_ui()
                self._refresh_current_table()
                self.notify("다중 선택이 취소되었습니다.")
                return

        if event.key == "right" and self.query_one("#sidebar").has_focus:
            self.query_one("#cmd-table").focus()
        elif event.key == "left" and self.query_one("#cmd-table").has_focus:
            if not getattr(self, "delete_mode", False):
                self.query_one("#sidebar").focus()

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """테이블 행 선택 시 동작 (기본 모드 시 복사)"""
        if getattr(self, "delete_mode", False):
            return
            
        if self.multi_selections:
            self._execute_multi_copy()
            return

        row_data = event.data_table.get_row(event.row_key)
        command_str = row_data[2]  # "명령어" 컬럼 인덱스
        
        self._handle_copy_with_variables(command_str)

    def _handle_copy_with_variables(self, command_str: str) -> None:
        """문자열 내 동적 변수를 파싱하여 팝업을 띄우거나 바로 복사하는 헬퍼 메서드"""
        # 정규식을 이용해 {{변수}} 추출
        variables = re.findall(r'\{\{(.*?)\}\}', command_str)
        
        if not variables:
            self.copy_to_clipboard(command_str)
            return
            
        # 중복 변수 제거 (순서 유지)
        seen = set()
        unique_vars = [x for x in variables if not (x in seen or seen.add(x))]
        
        def check_modal_result(result: dict | None) -> None:
            if result is not None:
                final_cmd = command_str
                for k, v in result.items():
                    final_cmd = final_cmd.replace(f"{{{{{k}}}}}", v)
                self.copy_to_clipboard(final_cmd)
                
        # 변수 입력 모달 띄우기
        self.push_screen(VariableModal(unique_vars), check_modal_result)

    def copy_to_clipboard(self, text: str) -> None:
        """명령어를 클립보드에 복사하고 우측 하단에 스낵바 알림을 띄움"""
        try:
            pyperclip.copy(text)
            self.notify(f"[{text}]", title="클립보드에 복사되었습니다!")
        except Exception as e:
            self.notify(f"복사 실패: {e}", title="오류", severity="error")

if __name__ == "__main__":
    app = CommandFlowApp()
    app.run()