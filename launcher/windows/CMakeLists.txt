# Windows frontend is separate; Linux keeps launcher/{builder,core,app}.
add_executable(ttt2-launcher WIN32 entry.cpp)
target_compile_features(ttt2-launcher PRIVATE cxx_std_20)
target_link_options(ttt2-launcher PRIVATE -municode -static)
target_link_libraries(ttt2-launcher PRIVATE advapi32 shell32)
find_package(Python3 REQUIRED COMPONENTS Interpreter)
add_test(NAME windows_launcher_backend_test COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/test_backend.py)
set_target_properties(ttt2-launcher PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
