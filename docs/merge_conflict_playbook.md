# Merge Conflict Playbook

PR에서 아래 파일 충돌이 반복될 때 빠르게 정리하는 절차입니다.

- `README.md`
- `agent/__init__.py`
- `agent/runtime.py`
- `main.py`
- `tests/test_team_runtime.py`

## 1) 베이스 브랜치 병합 시도

```bash
git fetch origin
git checkout <feature-branch>
git merge origin/<base-branch>
```

## 2) 자동 해소 스크립트 실행

```bash
./scripts/resolve_pr_conflicts.sh
```

스크립트가 하는 일:

- 충돌 파일에서 현재 브랜치(ours) 버전을 우선 선택
- 남은 충돌 유무 확인
- `py_compile`, `unittest` 자동 검증

## 3) 병합 커밋 생성

```bash
git commit -m "Resolve merge conflicts with base branch"
git push
```

## 참고

- 이 스크립트는 **이미 merge 중인 상태**(`.git/MERGE_HEAD` 존재)에서만 동작합니다.
- 추가 충돌 파일이 있으면 수동으로 해결 후 커밋하세요.
