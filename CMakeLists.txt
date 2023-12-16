cmake_minimum_required(VERSION 3.5)

project(phone_camera_import LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_subdirectory(modules/fmt)
add_subdirectory(modules/CLI11)

find_package(Boost COMPONENTS regex system filesystem REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS core imgproc highgui)
find_package(spdlog REQUIRED)
include_directories( ${OpenCV_INCLUDE_DIRS} )

add_executable(phone_camera_import main.cpp)
target_link_libraries(phone_camera_import PUBLIC
    Boost::regex
    Boost::system
    Boost::filesystem
    CLI11::CLI11
    spdlog::spdlog
    fmt::fmt
    ${OpenCV_LIBS}
    )

install(TARGETS phone_camera_import
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR})
