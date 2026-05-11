import re
import pyperclip
import threading
import platform
import keyboard
from thefuzz import fuzz
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Tree, DataTable, Input, Button, Label
from textual.containers import Horizontal, Vertical
from textual.binding import Binding
from textual.screen import ModalScreen
from textual import on
from database import DatabaseManager

def bring_to_front():
    """OS별 터미널 창 최상단 활성화 (글로벌 단축키 트리거 시 호출)"""
    system = platform.system()
    if system == "Windows":
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 5) # SW_SHOW
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

class ManageCommandModal(ModalScreen[int]):
    """명령어 관리(삭제) 모달 창"""

    CSS = """
    ManageCommandModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }
    #manage-modal-container {
        width: 50;
        height: auto;
        background: $surface;
        border: tall $error;
        padding: 1 2;
    }
    .manage-input {
        margin-bottom: 1;
    }
    #manage-button-container {
        align: right middle;
        height: auto;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="manage-modal-container"):
            yield Label("⚠️ 투플(명령어) 삭제 관리")
            yield Label("삭제할 명령어의 ID 번호를 입력하세요:")
            yield Input(placeholder="예: 3", id="input-delete-id", classes="manage-input")
            with Horizontal(id="manage-button-container"):
                yield Button("삭제", variant="error", id="btn-manage-delete")
                yield Button("취소", variant="primary", id="btn-manage-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-manage-delete":
            val = self.query_one("#input-delete-id", Input).value.strip()
            if val.isdigit():
                self.dismiss(int(val))
            else:
                self.app.notify("올바른 숫자 형태의 ID를 입력해주세요.", severity="error")
        elif event.button.id == "btn-manage-cancel":
            self.dismiss(None)

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
    ]

    def __init__(self):
        super().__init__()
        # DB 초기화 및 더미 데이터 준비
        self.db = DatabaseManager()
        self.db.init_db()
        self.db.insert_dummy_data()
        self.current_category = "모든 카테고리"

    def compose(self) -> ComposeResult:
        """UI 위젯을 화면에 배치합니다."""
        yield Header(show_clock=True)
        with Horizontal():
            yield Tree("모든 카테고리", id="sidebar")
            with Vertical(id="main-content"):
                with Horizontal(id="search-container"):
                    yield Input(placeholder="명령어, 설명, 태그 검색... (퍼지 검색)", id="search-input")
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
        table.add_columns("ID", "분류", "명령어", "설명", "태그")
        
        # 3. 최초 화면에 모든 명령어 데이터 로드
        self.load_all_commands()

    def load_all_commands(self):
        """모든 명령어를 테이블에 로드합니다."""
        commands = self.db.get_all_commands()
        self._populate_table(commands)

    def _populate_table(self, commands: list):
        """테이블 내용을 지우고 새로운 데이터로 채우는 헬퍼 메서드"""
        table = self.query_one("#cmd-table", DataTable)
        table.clear()
        for cmd in commands:
            table.add_row(
                str(cmd['id']),
                f"{cmd['large_category']} > {cmd['medium_category']}",
                cmd['command'],
                cmd['description'],
                cmd['tags']
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
                if self.current_category == "모든 카테고리":
                    self.load_all_commands()
                else:
                    self._populate_table(self.db.get_commands_by_category(self.current_category))
                    
        self.push_screen(AddCommandModal(), check_add_result)

    def action_manage(self) -> None:
        """'e' 키 입력 시 관리(삭제) 인터페이스 모달을 띄웁니다."""
        def check_manage_result(cmd_id: int | None) -> None:
            if cmd_id is not None:
                if self.db.delete_command(cmd_id):
                    self.notify(f"ID {cmd_id} 명령어가 성공적으로 삭제되었습니다.", title="삭제 완료")
                    
                    # 대분류가 모두 지워졌을 수 있으므로 트리 갱신
                    tree = self.query_one("#sidebar", Tree)
                    tree.clear()
                    categories = self.db.get_large_categories()
                    for cat in categories:
                        tree.root.add_leaf(cat)
                        
                    # 테이블 화면 갱신
                    if self.current_category == "모든 카테고리":
                        self.load_all_commands()
                    else:
                        self._populate_table(self.db.get_commands_by_category(self.current_category))
                else:
                    self.notify(f"해당 ID({cmd_id})를 가진 명령어를 찾을 수 없습니다.", severity="warning")
                    
        self.push_screen(ManageCommandModal(), check_manage_result)

    def action_search(self) -> None:
        """'/' 키 입력 시 검색창을 토글하고 포커스를 이동합니다."""
        search_container = self.query_one("#search-container")
        search_input = self.query_one("#search-input", Input)
        
        if search_container.has_class("-visible"):
            search_container.remove_class("-visible")
            search_input.value = "" # 검색어 초기화
            self.query_one("#cmd-table").focus()
            
            if self.current_category == "모든 카테고리":
                self.load_all_commands()
            else:
                self._populate_table(self.db.get_commands_by_category(self.current_category))
        else:
            search_container.add_class("-visible")
            search_input.focus()

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed) -> None:
        """검색어 입력 시 thefuzz를 이용한 퍼지 검색 수행"""
        query = event.value.strip().lower()
        
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
            if score > 40: # 유사도 임계값
                results.append((score, cmd))
                
        # 유사도 점수가 높은 순으로 정렬
        results.sort(key=lambda x: x[0], reverse=True)
        filtered_commands = [item[1] for item in results]
        self._populate_table(filtered_commands)

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
            
        if label == "모든 카테고리":
            self.load_all_commands()
        else:
            commands = self.db.get_commands_by_category(label)
            self._populate_table(commands)

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        """테이블 행 선택 시 명령어 추출 및 변수 모달 띄우기"""
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