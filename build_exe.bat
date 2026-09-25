@echo off
cd /d "%~dp0"
REM 개발 PC에서 한 번만 실행하면 dist\ExamCollector\ExamCollector.exe 가 만들어진다(Python 설치가 필요 없는 배포본).
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean ExamCollector.spec
echo.
echo 완료: dist\ExamCollector 폴더를 통째로 압축(zip)해서 제출/배포하세요.
pause
