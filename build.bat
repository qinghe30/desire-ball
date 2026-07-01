@echo off
chcp 65001 >nul
echo ========================================
echo  DesireBall 打包脚本
echo ========================================
echo.

:: 检查 PyInstaller 是否安装
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo [错误] PyInstaller 未安装，正在安装...
    pip install pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败，请手动运行: pip install pyinstaller
        pause
        exit /b 1
    )
)

echo [1/2] 正在打包，请稍候...
echo.

:: --onefile: 单文件输出
:: --noconsole: 无控制台窗口（pyw 文件自动处理）
:: --name: 输出文件名
:: --icon: 图标（如果存在）
pyinstaller --onefile --noconsole --name DesireBall desire_ball.pyw

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请检查上方错误信息。
    pause
    exit /b 1
)

echo.
echo [2/2] 清理临时文件...
rmdir /s /q build 2>nul
del /q *.spec 2>nul

echo.
echo ========================================
echo  打包完成！
echo  输出文件: dist\DesireBall.exe
echo ========================================
echo.
echo  双击运行测试，打包为 exe 后建议测试以下功能:
echo  - 程序是否能正常启动
echo  - 开机自启是否正常
echo  - 反馈功能是否正常发送
echo.
pause