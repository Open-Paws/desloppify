cmake_minimum_required(VERSION 3.20)
project(CxxFixture LANGUAGES CXX)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

add_executable(cxx_fixture src/main.cpp)
target_include_directories(cxx_fixture PRIVATE include)
