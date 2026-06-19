cmake_minimum_required(VERSION 3.16)
project(dune_client_probe_loader C)

add_library(dune_client_probe_loader SHARED dune_client_probe_loader.c)
target_compile_options(dune_client_probe_loader PRIVATE -std=c11 -Wall -Wextra -Wpedantic)
target_link_libraries(dune_client_probe_loader PRIVATE dl pthread)
set_target_properties(
  dune_client_probe_loader
  PROPERTIES
    OUTPUT_NAME dune_client_probe_loader
    POSITION_INDEPENDENT_CODE ON
)
