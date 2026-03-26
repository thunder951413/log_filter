Function RunPreviousUninstaller
  Exch $1
  Exch
  Exch $0
  Push $2
  Push $3
  StrCmp $0 "" done
  StrCpy $2 "$0\Uninstall ${APP_PRODUCT_FILENAME}.exe"
  IfFileExists "$2" 0 done
  DetailPrint "卸载旧版本: $0"
  ExecWait '"$2" /S /KEEP_APP_DATA $1 _?=$0' $3
  IntCmp $3 0 done failure failure
failure:
  MessageBox MB_ICONSTOP|MB_OK "旧版本卸载失败，安装已中止。请先手动关闭程序后重试。"
  Abort
done:
  Pop $3
  Pop $2
  Pop $0
  Pop $1
FunctionEnd

!macro cleanupStaleRegistry ROOT
  DeleteRegKey ${ROOT} "${INSTALL_REGISTRY_KEY}"
  DeleteRegKey ${ROOT} "${UNINSTALL_REGISTRY_KEY}"
  !ifdef UNINSTALL_REGISTRY_KEY_2
    DeleteRegKey ${ROOT} "${UNINSTALL_REGISTRY_KEY_2}"
  !endif
!macroend

!macro uninstallFromRegistry ROOT MODE LABEL
  ClearErrors
  ReadRegStr $0 ${ROOT} "${INSTALL_REGISTRY_KEY}" "InstallLocation"
  IfErrors 0 +2
  StrCpy $0 ""
  StrCmp $0 "" ${LABEL}_done
  StrCpy $1 "$0\Uninstall ${APP_PRODUCT_FILENAME}.exe"
  IfFileExists "$1" 0 ${LABEL}_cleanup_stale
  Push $0
  Push "${MODE}"
  Call RunPreviousUninstaller
  Goto ${LABEL}_done
${LABEL}_cleanup_stale:
  DetailPrint "清理陈旧注册表: ${ROOT} $0"
  !insertmacro cleanupStaleRegistry ${ROOT}
${LABEL}_done:
!macroend

!macro customInit
  SetRegView 64
  !insertmacro uninstallFromRegistry HKCU /currentuser HKCU64
  !insertmacro uninstallFromRegistry HKLM /allusers HKLM64
  SetRegView 32
  !insertmacro uninstallFromRegistry HKCU /currentuser HKCU32
  !insertmacro uninstallFromRegistry HKLM /allusers HKLM32
!macroend
