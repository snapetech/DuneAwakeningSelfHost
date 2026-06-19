cmake_minimum_required(VERSION 3.16)

project(dune_linux_server_loader LANGUAGES C)

add_library(dune_server_probe_loader SHARED dune_server_probe_loader.c)
target_compile_options(dune_server_probe_loader PRIVATE -std=c11 -Wall -Wextra -Wpedantic)
target_link_libraries(dune_server_probe_loader PRIVATE dl pthread)
set_target_properties(
  dune_server_probe_loader
  PROPERTIES
    OUTPUT_NAME dune_server_probe_loader
    POSITION_INDEPENDENT_CODE ON
)
