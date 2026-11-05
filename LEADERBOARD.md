# 외부 킬 순위 앱

`LeaderboardClient.py`는 현재 경기의 모드별 킬 순위를 별도 Windows 창에 표시합니다. 서버와 앱은 같은 신뢰할 수 있는 LAN에 두고, API는 읽기 전용이며 토큰 인증을 요구합니다.

## 서버 실행

PowerShell에서 서버를 시작하기 전에 32자 이상의 토큰을 설정합니다.

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:SANS_LEADERBOARD_TOKEN = "<위에서 생성한 토큰>"
python Server.py
```

토큰은 서버 로그나 소스 코드에 저장하지 마세요. 서버는 게임 포트(`SERVER_PORT`)와 별도로 `LEADERBOARD_PORT`를 사용합니다. 기본 주소는 `SERVER_IP`이며, 해당 IP가 서버 컴퓨터의 LAN 주소인지 확인하고 운영체제 방화벽에서 순위 포트의 LAN 연결만 허용하세요.

## 다른 PC에서 보기

다른 PC에서 `start_leaderboard.bat`을 더블 클릭합니다. Python이 설치되어 있으면 순위 창이 열립니다. 서버 PC의 LAN 주소와 서버 토큰을 넣고 **연결 / 새로고침**을 누르세요. 토큰을 확인할 때는 **표시**를 체크하고, Enter 키로 연결할 수도 있습니다. 앱은 2초마다 현재 경기 순위를 갱신합니다. 경기 중이 아닌 모드는 표시되지 않습니다. 자주 사용한다면 배치 파일을 우클릭해 바로가기를 만든 뒤 바탕 화면에 두면 됩니다.

서버와 앱을 같은 PC에서 실행한다면, 서버를 시작한 PowerShell에서 토큰을 설정하면 앱이 주소와 토큰을 자동으로 채웁니다. 다른 PC에서는 토큰을 직접 입력하거나 해당 PC에 `SANS_LEADERBOARD_TOKEN` 환경 변수를 설정할 수 있습니다.

기본 HTTP 연결은 LAN 내부에서만 사용하세요. 인터넷에 직접 공개하지 마세요.
