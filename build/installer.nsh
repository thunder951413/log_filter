!macro cleanupStaleRegistry ROOT
  DeleteRegKey ${ROOT} "${INSTALL_REGISTRY_KEY}"
  DeleteRegKey ${ROOT} "${UNINSTALL_REGISTRY_KEY}"
  !ifdef UNINSTALL_REGISTRY_KEY_2
    DeleteRegKey ${ROOT} "${UNINSTALL_REGISTRY_KEY_2}"
  !endif
!macroend

!macro cleanupStaleInstallation ROOT LABEL
  ClearErrors
  ReadRegStr $0 ${ROOT} "${INSTALL_REGISTRY_KEY}" "InstallLocation"
  IfErrors 0 +2
  StrCpy $0 ""
  StrCmp $0 "" ${LABEL}_done
  StrCpy $1 "$0\Uninstall ${APP_PRODUCT_FILENAME}.exe"
  IfFileExists "$1" ${LABEL}_done 0
  DetailPrint "清理陈旧注册表: ${ROOT} $0"
  !insertmacro cleanupStaleRegistry ${ROOT}
${LABEL}_done:
!macroend

!macro customInit
  SetRegView 64
  !insertmacro cleanupStaleInstallation HKCU HKCU64
  !insertmacro cleanupStaleInstallation HKLM HKLM64
  SetRegView 32
  !insertmacro cleanupStaleInstallation HKCU HKCU32
  !insertmacro cleanupStaleInstallation HKLM HKLM32
!macroend
