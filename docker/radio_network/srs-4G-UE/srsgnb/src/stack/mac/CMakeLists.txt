#
# Copyright 2013-2023 Software Radio Systems Limited
#
# This file is part of srsRAN
#
# srsRAN is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# srsRAN is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# A copy of the GNU Affero General Public License can be found in
# the LICENSE file in the top-level directory of this distribution
# and at http://www.gnu.org/licenses/.
#

if (NOT TARGET edgeric)
  find_package(Protobuf REQUIRED)
  set(EDGERIC_ROOT ${PROJECT_SOURCE_DIR}/../srsRAN-5G-ER/build)
  find_library(EDGERIC_LIB
    NAMES edgeric
    PATHS
      ${EDGERIC_ROOT}/lib
      ${EDGERIC_ROOT}/lib/edgeric
    NO_DEFAULT_PATH)
  if (NOT EDGERIC_LIB)
    message(FATAL_ERROR "libedgeric.a not found. Please build srsRAN-5G-ER first.")
  endif()

  add_library(edgeric STATIC IMPORTED GLOBAL)
  set_target_properties(edgeric PROPERTIES
    IMPORTED_LOCATION ${EDGERIC_LIB}
    INTERFACE_INCLUDE_DIRECTORIES "${PROJECT_SOURCE_DIR}/../srsRAN-5G-ER/lib/edgeric;${PROTOBUF_INCLUDE_DIRS}"
  )
  set_property(TARGET edgeric APPEND PROPERTY
    INTERFACE_LINK_LIBRARIES "${ZMQ_LIBRARIES};${Protobuf_LIBRARIES};zmq")
endif()

set(SOURCES mac_nr.cc
            ue_nr.cc
            sched_nr.cc
            sched_nr_ue.cc
            sched_ue/ue_cfg_manager.cc
            sched_nr_worker.cc
            sched_nr_grant_allocator.cc
            sched_nr_harq.cc
            sched_nr_pdcch.cc
            sched_nr_sch.cc
            sched_nr_cfg.cc
            sched_nr_helpers.cc
            sched_nr_bwp.cc
            sched_nr_rb.cc
            sched_nr_time_rr.cc
            harq_softbuffer.cc
            sched_nr_signalling.cc
            sched_nr_interface_utils.cc)

add_library(srsgnb_mac STATIC ${SOURCES})
target_link_libraries(srsgnb_mac srsenb_mac_common srsran_mac rrc_nr_asn1 edgeric)
include_directories(${PROJECT_SOURCE_DIR})
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/../../../../../srsRAN-5G-ER/lib)

add_subdirectory(test)
