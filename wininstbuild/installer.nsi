; This file is a part of ninfs.
;
; Copyright (c) 2017-2020 Ian Burgwin
; This file is licensed under The MIT License (MIT).
; You can find the full license text in LICENSE.md in the root of this project.

;NSIS Modern User Interface
;Basic Example Script
;Written by Joost Verburg

Unicode True

;--------------------------------
;Include Modern UI

  !include "MUI2.nsh"

;--------------------------------
;General

  !define REG_ROOT "HKCU"
  !define REG_PATH "Software\ninfs"

  !define NAME "ninfs ${VERSION}"

  !define WINFSP_MSI_NAME "winfsp-1.7.20172.msi"

  ;Name and file
  Name "${NAME}"
  OutFile "dist\ninfs-${VERSION}-win32-installer.exe"

  ;Default installation folder
  InstallDir "$LOCALAPPDATA\ninfs"
  
  ;Get installation folder from registry if available
  InstallDirRegKey "${REG_ROOT}" "${REG_PATH}" ""

  ;Request application privileges for Windows Vista
  RequestExecutionLevel user

  !include LogicLib.nsh

;--------------------------------
;Interface Settings

  !define MUI_ABORTWARNING

  !define MUI_STARTMENUPAGE_DEFAULTFOLDER "ninfs"
  !define MUI_STARTMENUPAGE_REGISTRY_ROOT "${REG_ROOT}"
  !define MUI_STARTMENUPAGE_REGISTRY_KEY "${REG_PATH}"
  !define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "Start Menu Folder"

;--------------------------------
;Pages

  !insertmacro MUI_PAGE_WELCOME
  !insertmacro MUI_PAGE_LICENSE "wininstbuild\licenses.txt"
  !insertmacro MUI_PAGE_COMPONENTS
  !insertmacro MUI_PAGE_DIRECTORY
  Var StartMenuFolder
  !insertmacro MUI_PAGE_STARTMENU "Application" $StartMenuFolder
  !insertmacro MUI_PAGE_INSTFILES
  !insertmacro MUI_PAGE_FINISH

  !define MUI_FINISHPAGE_TEXT "${NAME} has been uninstalled from your computer.$\r$\n$\r$\nNOTE: WinFsp needs to be removed separately if it is not being used for any other application."
  !insertmacro MUI_UNPAGE_CONFIRM
  !insertmacro MUI_UNPAGE_INSTFILES
  !insertmacro MUI_UNPAGE_FINISH

;--------------------------------
;Languages

  !insertmacro MUI_LANGUAGE "English"

;--------------------------------
;Installer Sections

Section "ninfs Application" SecInstall
  SectionIn RO

  SetOutPath "$INSTDIR"

  ReadRegStr $0 HKLM "SOFTWARE\WinFsp" "InstallDir"
  ${If} ${Errors}
    ; WinFsp needs installing
    File "wininstbuild\${WINFSP_MSI_NAME}"
    ExecWait 'msiexec /i "$INSTDIR\${WINFSP_MSI_NAME}" /passive'
  ${EndIf}

  File "LICENSE.md"
  File "README.md"
  File /r "build\exe.win32-3.8\"

  ;Store installation folder
  WriteRegStr HKCU "Software\ninfs" "" $INSTDIR
  
  ;Create uninstaller
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
  CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
  Delete "$SMPROGRAMS\$StartMenuFolder\ninfs*.lnk"
  CreateShortCut "$SMPROGRAMS\$StartMenuFolder\${NAME}.lnk" "$OUTDIR\ninfsw.exe" "" "$OUTDIR\lib\ninfs\gui\data\windows.ico"
  CreateShortCut "$SMPROGRAMS\$StartMenuFolder\Uninstall.lnk" "$OUTDIR\Uninstall.exe"
  !insertmacro MUI_STARTMENU_WRITE_END

SectionEnd

Section /o "Add to PATH" SecPATH
  ExecWait '"$INSTDIR/winpathmodify.exe" add "$INSTDIR"'
SectionEnd

;--------------------------------
;Descriptions

  LangString DESC_SecInstall ${LANG_ENGLISH} "The main ninfs application."
  LangString DESC_SecPATH ${LANG_ENGLISH} "Add the install directory to PATH for command line use."

  !insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecInstall} $(DESC_SecInstall)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecPATH} $(DESC_SecPATH)
  !insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------
;Uninstaller Section

Section "Uninstall" SecUninstall

  !insertmacro MUI_STARTMENU_GETFOLDER Application $StartMenuFolder
  Delete "$SMPROGRAMS\$StartMenuFolder\ninfs*.lnk"
  Delete "$SMPROGRAMS\$StartMenuFolder\uninstall.lnk"
  RMDir "$SMPROGRAMS\$StartMenuFolder"

  ExecWait '"$INSTDIR/winpathmodify.exe" remove "$INSTDIR"'

  Delete "$INSTDIR\LICENSE.md"
  Delete "$INSTDIR\README.md"
  Delete "$INSTDIR\api-ms-win-crt-*.dll"
  Delete "$INSTDIR\python3.dll"
  Delete "$INSTDIR\python38.dll"
  Delete "$INSTDIR\vcruntime140.dll"
  Delete "$INSTDIR\ninfs.exe"
  Delete "$INSTDIR\ninfsw.exe"
  Delete "$INSTDIR\winpathmodify.exe"
  Delete "$INSTDIR\winfsp*.msi"
  RMDir /r "$INSTDIR\lib"

  Delete "$INSTDIR\Uninstall.exe"

  RMDir "$INSTDIR"

  DeleteRegKey /ifempty HKCU "Software\ninfs"

SectionEnd
