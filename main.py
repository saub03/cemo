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

def minimize_window():
    """OS별 터미널 창 최소화 (복사 완료 시 호출)"""
    system = platform.system()
    if system == "Windows":
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6) # SW_MINIMIZE (6)
    elif system == "Darwin":
        import subprocess
        subprocess.run(["osascript", "-e", 'tell application "Terminal" to set miniaturized of front window to true'], check=False)
    elif system == "Linux":
        import subprocess
        try:
            subprocess.run(["wmctrl", "-r", "Command-Flow", "-b", "add,hidden"], check=False)
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
            result = {}
            for var in self.variables:
                val = self.query_one(f"#input-{var}", Input).value
                result[var] = val
            self.dismiss(result)
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

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
• [u]자동 복사 및 최소화[/u]: 명령어를 선택(Enter)하면 클립보드에 자동 복사되고 
                창이 최소화됩니다.
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
• [b]Enter[/b] : 명령어 복사 (삭제 모드 시: 체크박스 선택 토글)
• [b]ESC[/b] : 팝업 창 닫기, 검색창 닫기, 삭제 모드 취소
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
    ]

    def __init__(self):
        super().__init__()
        # DB 초기화 및 더미 데이터 준비
        self.db = DatabaseManager()
        self.db.init_db()
        self.db.insert_dummy_data()
        self.current_category = "모든 카테고리"
        self.delete_mode = False
        self.delete_selections = set()

    def compose(self) -> ComposeResult:
        """UI 위젯을 화면에 배치합니다."""
        yield Header(show_clock=True)
        with Horizontal():
            yield Tree("모든 카테고리", id="sidebar")
            with Vertical(id="main-content"):
                with Horizontal(id="search-container"):
                    yield SearchInput(placeholder="명령어, 설명, 태그 검색... (퍼지 검색)", id="search-input")
                yield DataTable(id="cmd-table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        """UI 요소가 마운트될 때 실행되는 초기화 로직"""
        self.title = "Command-Flow"
        
        # 글로벌 단축키(백그라운드 스레드) 등록
        self._start_hotkey_thread()

        # 1. 사이드바 트리 초기화
        tree = self.query_one("#sidebar", Tree)
        tree.root.expand()
        categories = self.db.get_large_categories()
        for cat in categories:
            tree.root.add_leaf(cat)
            
        # 2. 메인 데이터 테이블 컬럼 설정
        table = self.query_one("#cmd-table", DataTable)
        table.add_column("ID", key="id")
        table.add_column("분류", key="category")
        table.add_column("명령어", key="command")
        table.add_column("설명", key="desc")
        table.add_column("태그", key="tags")
        
        # 3. 최초 화면에 모든 명령어 데이터 로드
        self._refresh_current_table()

    def _refresh_current_table(self) -> None:
        """현재 카테고리와 검색어를 기준으로 테이블 데이터를 갱신합니다."""
        query = self.query_one("#search-input", Input).value.strip().lower()
        if self.current_category == "모든 카테고리":
            target_commands = self.db.get_all_commands()
        else:
            target_commands = self.db.get_commands_by_category(self.current_category)
        
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
            else:
                id_display = str(cmd_id)
                
            table.add_row(
                id_display,
                f"{cmd['large_category']} > {cmd['medium_category']}",
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
                
                # 트리 초기화 및 재구성 (새로운 대분류가 추가됐을 수 있으므로)
                tree = self.query_one("#sidebar", Tree)
                tree.clear()
                categories = self.db.get_large_categories()
                for cat in categories:
                    tree.root.add_leaf(cat)
                
                # 테이블 화면 갱신
                self._refresh_current_table()
                    
        self.push_screen(AddCommandModal(), check_add_result)

    def action_manage(self) -> None:
        """'e' 키 입력 시 관리(삭제) 모드를 토글합니다."""
        if not self.delete_mode:
            self.delete_mode = True
            self.delete_selections = set()
            self.notify("삭제 모드: Enter로 삭제할 항목 선택 후, e를 다시 누르세요. (ESC: 취소)", timeout=5)
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
                    
                    # 대분류가 모두 지워졌을 수 있으므로 트리 갱신
                    tree = self.query_one("#sidebar", Tree)
                    tree.clear()
                    categories = self.db.get_large_categories()
                    for cat in categories:
                        tree.root.add_leaf(cat)
                        
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
        label = str(event.node.label)
        self.current_category = label
        
        # 카테고리 변경 시 기존 검색어가 있다면 초기화
        search_input = self.query_one("#search-input", Input)
        if search_input.value:
            search_input.value = ""
            
        self._refresh_current_table()
            
        # 카테고리 선택 후 메인 테이블(DataTable)로 자동 포커스 이동
        self.query_one("#cmd-table").focus()

    def on_key(self, event: events.Key) -> None:
        """ESC 키 삭제 모드 취소 및 좌/우 방향키 포커스 이동"""
        if event.key == "escape" and getattr(self, "delete_mode", False):
            self.delete_mode = False
            self.delete_selections.clear()
            self.notify("삭제 모드가 취소되었습니다.")
            self._refresh_current_table()
            return

        if event.key == "right" and self.query_one("#sidebar").has_focus:
            self.query_one("#cmd-table").focus()
        elif event.key == "left" and self.query_one("#cmd-table").has_focus:
            if not getattr(self, "delete_mode", False):
                self.query_one("#sidebar").focus()

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """테이블 행 선택 시 동작 (삭제 모드 시 선택 토글, 기본 모드 시 복사)"""
        if getattr(self, "delete_mode", False):
            cmd_id = int(event.row_key.value)
            if cmd_id in self.delete_selections:
                self.delete_selections.remove(cmd_id)
            else:
                self.delete_selections.add(cmd_id)
            
            new_display = f"[{'x' if cmd_id in self.delete_selections else ' '}] {cmd_id}"
            event.data_table.update_cell(event.row_key, "id", new_display)
            return

        row_data = event.data_table.get_row(event.row_key)
        command_str = row_data[2]  # "명령어" 컬럼 인덱스
        
        # 정규식을 이용해 {{변수}} 추출
        variables = re.findall(r'\{\{(.*?)\}\}', command_str)
        
        if variables:
            # 중복 변수 제거 (순서 유지)
            seen = set()
            unique_vars = [x for x in variables if not (x in seen or seen.add(x))]
            
            def check_modal_result(result: dict | None) -> None:
                if result is not None:
                    final_cmd = command_str
                    for k, v in result.items():
                        # {{변수}}를 입력받은 값으로 치환
                        final_cmd = final_cmd.replace(f"{{{{{k}}}}}", v)
                    self.copy_to_clipboard(final_cmd)
                    
            # 변수 입력 모달 띄우기
            self.push_screen(VariableModal(unique_vars), check_modal_result)
        else:
            # 변수가 없으면 바로 복사
            self.copy_to_clipboard(command_str)

    def copy_to_clipboard(self, text: str) -> None:
        """명령어를 클립보드에 복사하고 우측 하단에 스낵바 알림을 띄움"""
        try:
            pyperclip.copy(text)
            self.notify(f"[{text}]", title="클립보드에 복사되었습니다!")
            minimize_window()
        except Exception as e:
            self.notify(f"복사 실패: {e}", title="오류", severity="error")

if __name__ == "__main__":
    app = CommandFlowApp()
    app.run()