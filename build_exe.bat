@echo off
set PY="C:\Users\Yanis\AppData\Local\Python\pythoncore-3.14-64\python.exe"

echo Installing dependencies...
%PY% -m pip install pyinstaller pillow requests -q

echo.
echo Building DGGG.exe ...
%PY% -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "DGGG" ^
    main.py

echo.
echo Done!  Find DGGG.exe in the dist\ folder.
echo Copy the games\ folder next to the exe before distributing.
pause
