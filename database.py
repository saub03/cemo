import sqlite3
import os

class DatabaseManager:
    def __init__(self, db_path="command_flow.db"):
        self.db_path = db_path

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        """데이터베이스 및 테이블 초기화"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    large_category TEXT,
                    medium_category TEXT,
                    small_category TEXT,
                    command TEXT,
                    description TEXT,
                    tags TEXT,
                    usage_count INTEGER DEFAULT 0
                )
            ''')
            conn.commit()

    def insert_dummy_data(self):
        """테스트를 위한 더미 데이터 삽입"""
        dummy_data = [
            ("git", "commit", "basic", 'git commit -m "{{message}}"', "Git 커밋 메시지 작성", "git,commit", 0),
            ("git", "branch", "create", 'git checkout -b {{branch_name}}', "새로운 브랜치 생성 및 이동", "git,branch", 0),
            ("git", "status", "basic", 'git status', "작업 디렉토리와 스테이징 영역의 상태 확인", "git,status", 0),
            ("git", "add", "basic", 'git add .', "변경된 모든 파일을 스테이징 영역에 추가", "git,add", 0),
            ("git", "pull", "remote", 'git pull origin {{branch_name}}', "원격 저장소의 변경 사항을 가져와 병합", "git,pull,remote", 0),
            ("git", "push", "remote", 'git push origin {{branch_name}}', "로컬 브랜치의 변경 사항을 원격 저장소에 업로드", "git,push,remote", 0),
            ("git", "log", "history", 'git log --oneline --graph', "커밋 히스토리를 한 줄로 그래프와 함께 보기", "git,log,history", 0),
            ("git", "reset", "undo", 'git reset --soft HEAD~1', "최근 커밋 취소 (변경 사항 유지)", "git,reset,undo", 0),
            ("docker", "container", "run", 'docker run -d -p {{port}}:80 --name {{name}} nginx', "Nginx 컨테이너 백그라운드 실행", "docker,nginx", 0),
            ("linux", "file", "search", 'find . -name "{{filename}}"', "현재 디렉토리에서 파일 이름으로 검색", "linux,find", 0),
            ("aws", "s3", "sync", 'aws s3 sync {{local_dir}} s3://{{bucket_name}}', "로컬 디렉토리를 S3 버킷과 동기화", "aws,s3", 0)
        ]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM commands')
            if cursor.fetchone()[0] == 0:
                cursor.executemany('''
                    INSERT INTO commands (
                        large_category, medium_category, small_category, command, description, tags, usage_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', dummy_data)
                conn.commit()
                return True
            return False

    def insert_command(self, large_category, medium_category, small_category, command, description, tags):
        """새로운 명령어를 데이터베이스에 추가"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO commands (
                    large_category, medium_category, small_category, command, description, tags, usage_count
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
            ''', (large_category, medium_category, small_category, command, description, tags))
            conn.commit()

    def delete_command(self, cmd_id):
        """특정 ID의 명령어를 삭제"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM commands WHERE id = ?', (cmd_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted

    def get_all_commands(self):
        """모든 명령어 데이터를 가져옴"""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row # 딕셔너리 형태로 결과 반환
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM commands ORDER BY usage_count DESC, id ASC')
            return [dict(row) for row in cursor.fetchall()]

    def get_large_categories(self):
        """대분류 카테고리 목록을 가져옴"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT large_category FROM commands ORDER BY large_category ASC')
            return [row[0] for row in cursor.fetchall()]

    def get_category_tree(self):
        """대분류와 중분류의 계층 구조를 딕셔너리로 반환"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT large_category, medium_category FROM commands ORDER BY large_category ASC, medium_category ASC')
            tree = {}
            for l_cat, m_cat in cursor.fetchall():
                if l_cat not in tree:
                    tree[l_cat] = []
                if m_cat and m_cat not in tree[l_cat]:
                    tree[l_cat].append(m_cat)
            return tree

    def get_commands_by_category(self, large_category):
        """특정 대분류의 명령어 데이터를 가져옴"""
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM commands WHERE large_category = ? ORDER BY usage_count DESC, id ASC', (large_category,))
            return [dict(row) for row in cursor.fetchall()]

if __name__ == "__main__":
    # 단독 실행 시 DB 초기화 및 더미 데이터 삽입 테스트 
    db = DatabaseManager()
    db.init_db()
    if db.insert_dummy_data():
        print("더미 데이터가 성공적으로 추가되었습니다.")
    else:
        print("데이터가 이미 존재합니다.")

    commands = db.get_all_commands()
    print(f"\n총 {len(commands)}개의 명령어가 있습니다.")
    for cmd in commands:
        print(f"[{cmd['large_category']}] {cmd['command']} - {cmd['description']}")