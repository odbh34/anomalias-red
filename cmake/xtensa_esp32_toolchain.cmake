set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR xtensa)

set(TOOLCHAIN_DIR C:/Users/OscarD/.platformio/packages/toolchain-xtensa-esp32)
set(CMAKE_C_COMPILER ${TOOLCHAIN_DIR}/bin/xtensa-esp32-elf-gcc.exe)
set(CMAKE_ASM_COMPILER ${TOOLCHAIN_DIR}/bin/xtensa-esp32-elf-gcc.exe)
set(CMAKE_CXX_COMPILER ${TOOLCHAIN_DIR}/bin/xtensa-esp32-elf-g++.exe)
set(CMAKE_AR ${TOOLCHAIN_DIR}/bin/xtensa-esp32-elf-ar.exe)
set(CMAKE_RANLIB ${TOOLCHAIN_DIR}/bin/xtensa-esp32-elf-ranlib.exe)

set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
