#ifndef EDGERIC_H
#define EDGERIC_H

#include <fstream>
#include <iostream>
#include <map>
#include <tuple>
#include <zmq.hpp>

#include "control_mcs.pb.h"
#include "control_weights.pb.h"
#include "metrics.pb.h"

class edgeric {
private:
    // --- Received control data from EdgeRIC µApps ---
    static std::map<uint16_t, float>   weights_recved;
    static std::map<uint16_t, uint8_t> mcs_recved;

    // --- Metrics collected from the RAN stack ---
    static std::map<uint16_t, float>    ue_cqis;
    static std::map<uint16_t, float>    ue_snrs;
    static std::map<uint16_t, float>    rx_bytes;
    static std::map<uint16_t, float>    tx_bytes;
    static std::map<uint16_t, uint32_t> ue_ul_buffers;
    static std::map<uint16_t, uint32_t> ue_dl_buffers;
    static std::map<uint16_t, float>    dl_tbs_ues;

    // --- HARQ feedback and TX attempt tracking ---
    static std::map<uint16_t, bool> ul_harq_ack;
    static std::map<uint16_t, bool> ul_tx_attempt;

    // --- Internal state ---
    static uint32_t er_ran_index_weights;
    static uint32_t er_ran_index_mcs;
    static bool enable_logging;
    static bool initialized;

    static void ensure_initialized();

public:
    static uint32_t tti_cnt;

    // --- Initialization ---
    static void init();
    static void setTTI(uint32_t tti_count) { tti_cnt = tti_count; }

    // --- Logging utility ---
    static void printmyvariables();

    // --- Metric setters ---
    static void set_cqi(uint16_t rnti, float cqi) { ue_cqis[rnti] = cqi; }
    static void set_snr(uint16_t rnti, float snr) { ue_snrs[rnti] = snr; }
    static void set_ul_buffer(uint16_t rnti, uint32_t ul_buffer) { ue_ul_buffers[rnti] = ul_buffer; }
    static void set_dl_buffer(uint16_t rnti, uint32_t dl_buffer) { ue_dl_buffers[rnti] = dl_buffer; }
    static void set_tx_bytes(uint16_t rnti, float tbs) { tx_bytes[rnti] += tbs; }
    static void set_rx_bytes(uint16_t rnti, float tbs) { rx_bytes[rnti] += tbs; }
    static void set_dl_tbs(uint16_t rnti, float tbs) { dl_tbs_ues[rnti] = tbs; }

    // --- Explicit HARQ + attempt tracking ---
    static void set_ul_tx_attempt(uint16_t rnti, bool attempt);
    static void set_ul_harq_ack(uint16_t rnti, bool ack);

    // --- Real-time E2 messaging ---
    static void send_to_er();           // Publish RT-E2 Report
    static void get_weights_from_er();  // Receive RT-E2 Policy (weights)
    static void get_mcs_from_er();      // Receive RT-E2 Policy (MCS)

    // --- Static getters for policies ---
    static bool get_weights(uint16_t rnti, float& value);
    static bool get_mcs(uint16_t rnti, uint8_t& value);
};

#endif // EDGERIC_H
