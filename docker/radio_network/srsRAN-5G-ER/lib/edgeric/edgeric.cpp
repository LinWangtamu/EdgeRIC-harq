#include "edgeric.h"

// -----------------------------------------------------------------------------
// Static member variable definitions
// -----------------------------------------------------------------------------
uint32_t edgeric::tti_cnt = 0;
uint32_t edgeric::er_ran_index_weights = 0;
uint32_t edgeric::er_ran_index_mcs = 0;

std::map<uint16_t, float>    edgeric::ue_cqis = {};
std::map<uint16_t, float>    edgeric::ue_snrs = {};
std::map<uint16_t, float>    edgeric::rx_bytes = {};
std::map<uint16_t, float>    edgeric::tx_bytes = {};
std::map<uint16_t, uint32_t> edgeric::ue_ul_buffers = {};
std::map<uint16_t, uint32_t> edgeric::ue_dl_buffers = {};
std::map<uint16_t, float>    edgeric::dl_tbs_ues = {};

std::map<uint16_t, bool> edgeric::ul_harq_ack = {};
std::map<uint16_t, bool> edgeric::ul_tx_attempt = {};

std::map<uint16_t, float>   edgeric::weights_recved = {};
std::map<uint16_t, uint8_t> edgeric::mcs_recved = {};

bool edgeric::enable_logging = false;
bool edgeric::initialized = false;

// -----------------------------------------------------------------------------
// ZeroMQ context and sockets
// -----------------------------------------------------------------------------
zmq::context_t context;
zmq::socket_t publisher(context, ZMQ_PUB);
zmq::socket_t subscriber_weights(context, ZMQ_SUB);
zmq::socket_t subscriber_mcs(context, ZMQ_SUB);

// -----------------------------------------------------------------------------
// Initialization and setup
// -----------------------------------------------------------------------------
void edgeric::init()
{
    publisher.bind("tcp://10.53.2.4:5050");

    subscriber_weights.connect("tcp://10.53.2.5:5051");
    subscriber_weights.setsockopt(ZMQ_SUBSCRIBE, "", 0);
    int conflate = 1;
    subscriber_weights.setsockopt(ZMQ_CONFLATE, &conflate, sizeof(conflate));

    subscriber_mcs.connect("tcp://10.53.2.5:5052");
    subscriber_mcs.setsockopt(ZMQ_SUBSCRIBE, "", 0);
    subscriber_mcs.setsockopt(ZMQ_CONFLATE, &conflate, sizeof(conflate));

    initialized = true;
}

void edgeric::ensure_initialized()
{
    if (!initialized)
        init();
}

// -----------------------------------------------------------------------------
// HARQ and UL transmission tracking
// -----------------------------------------------------------------------------
void edgeric::set_ul_tx_attempt(uint16_t rnti, bool attempt)
{
    ul_tx_attempt[rnti] = attempt;
}

void edgeric::set_ul_harq_ack(uint16_t rnti, bool ack)
{
    ul_harq_ack[rnti] = ack;
}

// -----------------------------------------------------------------------------
// Send real-time UE metrics to EdgeRIC
// -----------------------------------------------------------------------------
void edgeric::send_to_er()
{
    ensure_initialized();

    Metrics metrics_msg;
    metrics_msg.set_tti_cnt(tti_cnt);

    for (const auto& ue_pair : ue_cqis) {
        uint16_t rnti = ue_pair.first;
        UeMetrics* ue_metrics = metrics_msg.add_ue_metrics();
        ue_metrics->set_rnti(rnti);
        ue_metrics->set_cqi(static_cast<uint32_t>(ue_pair.second));

        // Optional fields (safe lookup)
        ue_metrics->set_snr(ue_snrs.count(rnti) ? ue_snrs[rnti] : 0.0f);
        ue_metrics->set_tx_bytes(tx_bytes.count(rnti) ? tx_bytes[rnti] : 0.0f);
        ue_metrics->set_rx_bytes(rx_bytes.count(rnti) ? rx_bytes[rnti] : 0.0f);
        ue_metrics->set_dl_buffer(ue_dl_buffers.count(rnti) ? ue_dl_buffers[rnti] : 0);
        ue_metrics->set_ul_buffer(ue_ul_buffers.count(rnti) ? ue_ul_buffers[rnti] : 0);
        ue_metrics->set_dl_tbs(dl_tbs_ues.count(rnti) ? dl_tbs_ues[rnti] : 0);

        // HARQ + TX flags
        const bool ack = ul_harq_ack.count(rnti) ? ul_harq_ack[rnti] : false;
        const bool attempt = ul_tx_attempt.count(rnti) ? ul_tx_attempt[rnti] : false;

        ue_metrics->set_ul_harq_ack(ack);
        ue_metrics->set_ul_tx_attempt(attempt);
    }

    // Serialize
    std::string serialized_msg;
    if (!metrics_msg.SerializeToString(&serialized_msg)) {
        std::cerr << "[edgeric] Failed to serialize Metrics message.\n";
        return;
    }

    zmq::message_t zmq_msg(serialized_msg.size());
    memcpy(zmq_msg.data(), serialized_msg.data(), serialized_msg.size());
    publisher.send(zmq_msg, zmq::send_flags::dontwait);

    // Clear after publishing
    ue_cqis.clear();
    ue_snrs.clear();
    tx_bytes.clear();
    rx_bytes.clear();
    dl_tbs_ues.clear();
    ul_harq_ack.clear();
    ul_tx_attempt.clear();
}

// -----------------------------------------------------------------------------
// Receive policy (weights) from EdgeRIC
// -----------------------------------------------------------------------------
void edgeric::get_weights_from_er()
{
    ensure_initialized();
    zmq::message_t recv_message_er;
    zmq::recv_result_t size = subscriber_weights.recv(recv_message_er, zmq::recv_flags::dontwait);

    if (size) {
        SchedulingWeights weights_msg;
        if (weights_msg.ParseFromArray(recv_message_er.data(), recv_message_er.size())) {
            er_ran_index_weights = weights_msg.ran_index();

            float total_weight = 0.0f;
            weights_recved.clear();

            for (int i = 0; i < weights_msg.weights_size(); i += 2) {
                uint16_t rnti = static_cast<uint16_t>(weights_msg.weights(i));
                float weight = weights_msg.weights(i + 1);
                weights_recved[rnti] = weight;
                total_weight += weight;
            }

            if (total_weight > 0.0f) {
                for (auto& kv : weights_recved)
                    kv.second /= total_weight;
            }
        } else {
            std::cerr << "[edgeric] Failed to parse SchedulingWeights message.\n";
        }
    }
}

// -----------------------------------------------------------------------------
// Receive policy (MCS) from EdgeRIC
// -----------------------------------------------------------------------------
void edgeric::get_mcs_from_er()
{
    ensure_initialized();
    zmq::message_t recv_message_er;
    zmq::recv_result_t size = subscriber_mcs.recv(recv_message_er, zmq::recv_flags::dontwait);

    if (size) {
        mcs_control mcs_msg;
        if (mcs_msg.ParseFromArray(recv_message_er.data(), recv_message_er.size())) {
            er_ran_index_mcs = mcs_msg.ran_index();

            mcs_recved.clear();
            for (int i = 0; i < mcs_msg.mcs_size(); i += 2) {
                uint16_t rnti = static_cast<uint16_t>(mcs_msg.mcs(i));
                uint8_t mcs = mcs_msg.mcs(i + 1);
                mcs_recved[rnti] = mcs;
            }
        } else {
            std::cerr << "[edgeric] Failed to parse mcs_control message.\n";
        }
    }
}

// -----------------------------------------------------------------------------
// Policy getters
// -----------------------------------------------------------------------------
bool edgeric::get_weights(uint16_t rnti, float& value)
{
    auto it = weights_recved.find(rnti);
    if (it == weights_recved.end())
        return false;
    value = it->second;
    return true;
}

bool edgeric::get_mcs(uint16_t rnti, uint8_t& value)
{
    auto it = mcs_recved.find(rnti);
    if (it == mcs_recved.end())
        return false;
    value = it->second;
    return true;
}

// -----------------------------------------------------------------------------
// Logging helper (optional for debugging)
// -----------------------------------------------------------------------------
void edgeric::printmyvariables()
{
    if (!enable_logging)
        return;

    std::ofstream logfile("log.txt", std::ios_base::app);
    if (!logfile.is_open())
        return;

    logfile << "TTI: " << tti_cnt
            << ", Weights Index: " << er_ran_index_weights
            << ", MCS Index: " << er_ran_index_mcs << "\n";

    for (const auto& cqi_pair : ue_cqis) {
        uint16_t rnti = cqi_pair.first;
        logfile << "RNTI: " << rnti
                << " CQI: " << ue_cqis[rnti]
                << " SNR: " << (ue_snrs.count(rnti) ? ue_snrs[rnti] : 0)
                << " TxBytes: " << (tx_bytes.count(rnti) ? tx_bytes[rnti] : 0)
                << " RxBytes: " << (rx_bytes.count(rnti) ? rx_bytes[rnti] : 0)
                << " ULBuf: " << (ue_ul_buffers.count(rnti) ? ue_ul_buffers[rnti] : 0)
                << " DLTBS: " << (dl_tbs_ues.count(rnti) ? dl_tbs_ues[rnti] : 0)
                << " UL_TX_ATTEMPT: " << (ul_tx_attempt.count(rnti) ? ul_tx_attempt[rnti] : 0)
                << " UL_HARQ_ACK: " << (ul_harq_ack.count(rnti) ? ul_harq_ack[rnti] : 0)
                << std::endl;
    }

    logfile.close();
}
