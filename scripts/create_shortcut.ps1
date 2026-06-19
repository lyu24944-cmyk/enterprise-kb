$ProjectRoot = "C:\Users\Administrator\Desktop\Cursor\enterprise-kb"
$BatPath = Join-Path $ProjectRoot "运行演示.bat"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Enterprise-KB.lnk"

$Wsh = New-Object -ComObject WScript.Shell
$Shortcut = $Wsh.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $BatPath
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description = "Enterprise Knowledge Base - AI Agent + RAG"
$Shortcut.WindowStyle = 1
$Shortcut.Save()

Write-Host "Shortcut created: $ShortcutPath"
