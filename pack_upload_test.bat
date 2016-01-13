C:/tools/pythonx86_32/python.exe c:/Users/Rui/PycharmProjects/VOConverter/update_version.py
copy /y c:\Users\Rui\PycharmProjects\VOConverter\version.ini c:\Users\Rui\PycharmProjects\VOConverter\dist\version.ini
robocopy /E c:\Users\Rui\PycharmProjects\VOConverter\data\ c:\Users\Rui\PycharmProjects\VOConverter\dist\data\
C:/tools/pythonx86_32/python.exe c:/tools/python/Scripts/cxfreeze c:/Users/Rui/PycharmProjects/VOConverter/upload_aws.py --target-name=voconvteste.exe --icon=c:/Users/Rui/PycharmProjects/VOConverter/icon.ico
