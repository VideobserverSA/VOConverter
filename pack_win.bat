copy /y c:\Users\Rui\PycharmProjects\VOConverter\version.ini c:\Users\Rui\PycharmProjects\VOConverter\dist\version.ini
robocopy /E c:\Users\Rui\PycharmProjects\VOConverter\lang\ c:\Users\Rui\PycharmProjects\VOConverter\dist\lang\
C:/tools/pythonx86_32/python.exe c:/tools/python/Scripts/cxfreeze c:/Users/Rui/PycharmProjects/VOConverter/main.py --target-name=voconverter.exe --icon=c:/Users/Rui/PycharmProjects/VOConverter/icon.ico
