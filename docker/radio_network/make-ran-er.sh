set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}"
PROTO_SRC_DIR="${ROOT_DIR}/srsRAN-5G-ER/lib/protobufs"
PROTO_CPP_OUT="${ROOT_DIR}/srsRAN-5G-ER/lib/edgeric"
PROTO_PY_OUT="${ROOT_DIR}/../edgeric-v2"

echo "Generating protobuf sources with container protoc..."
protoc -I"${PROTO_SRC_DIR}" --cpp_out="${PROTO_CPP_OUT}" \
  control_mcs.proto control_weights.proto metrics.proto
#protoc -I"${PROTO_SRC_DIR}" --python_out="${PROTO_PY_OUT}" \
#  control_mcs.proto control_weights.proto metrics.proto

echo "Building srsRAN-5G-ER (gNB)..."
cd "${ROOT_DIR}/srsRAN-5G-ER"
rm -rf build
mkdir build
cd build
#cmake ../ -DCMAKE_BUILD_TYPE=Debug -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON
cmake ../ -DENABLE_EXPORT=ON -DENABLE_ZEROMQ=ON
make -j 8

echo "Building srs-4G-UE (UE)..."
cd "${ROOT_DIR}/srs-4G-UE"
rm -rf build
mkdir build
cd build
cmake ../ -DCMAKE_CXX_FLAGS="-I../../srsRAN-5G-ER/lib"
#cmake ../
make -j 8
