#include <cmath>
#include <cstdint>
#include <algorithm>
#include <iostream>
#include <string>
#include <vector>

namespace {

int parse_int_arg(int argc, char** argv, const std::string& name, int fallback) {
    for (int index = 1; index + 1 < argc; ++index) {
        if (argv[index] == name) {
            try {
                return std::max(1, std::stoi(argv[index + 1]));
            } catch (...) {
                return fallback;
            }
        }
    }
    return fallback;
}

int16_t read_i16_le(const char* data) {
    const auto lo = static_cast<uint8_t>(data[0]);
    const auto hi = static_cast<uint8_t>(data[1]);
    return static_cast<int16_t>(lo | (hi << 8));
}

int rms_for_samples(const std::vector<int16_t>& samples) {
    if (samples.empty()) {
        return 0;
    }
    long double sum = 0.0L;
    for (const int16_t sample : samples) {
        const long double value = static_cast<long double>(sample);
        sum += value * value;
    }
    return static_cast<int>(std::llround(std::sqrt(sum / samples.size())));
}

}  // namespace

int main(int argc, char** argv) {
    const int sample_rate = parse_int_arg(argc, argv, "--sample-rate", 8000);
    const int window_ms = parse_int_arg(argc, argv, "--window-ms", 500);
    const int samples_per_window = std::max(1, sample_rate * window_ms / 1000);
    const int bytes_per_window = samples_per_window * 2;
    const int min_partial_bytes = std::max(2, bytes_per_window / 2);

    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    std::vector<char> bytes(bytes_per_window);
    std::vector<int16_t> samples;
    samples.reserve(samples_per_window);

    int window_index = 0;
    while (true) {
        std::cin.read(bytes.data(), bytes_per_window);
        const std::streamsize bytes_read = std::cin.gcount();
        if (bytes_read < min_partial_bytes) {
            break;
        }

        samples.clear();
        const std::streamsize even_bytes = bytes_read - (bytes_read % 2);
        for (std::streamsize offset = 0; offset + 1 < even_bytes; offset += 2) {
            samples.push_back(read_i16_le(bytes.data() + offset));
        }

        std::cout << window_index << ' ' << rms_for_samples(samples) << '\n';
        ++window_index;

        if (bytes_read < bytes_per_window) {
            break;
        }
    }

    return 0;
}
