#include <algorithm>
#include <cmath>
#include <cstdint>
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

double gray_at(const std::vector<uint8_t>& frame, int pixel) {
    const int offset = pixel * 3;
    return frame[offset] * 0.299 + frame[offset + 1] * 0.587 + frame[offset + 2] * 0.114;
}

double saturation_for_rgb(uint8_t r, uint8_t g, uint8_t b) {
    const double max_value = std::max({static_cast<double>(r), static_cast<double>(g), static_cast<double>(b)});
    const double min_value = std::min({static_cast<double>(r), static_cast<double>(g), static_cast<double>(b)});
    if (max_value <= 0.0) {
        return 0.0;
    }
    return (max_value - min_value) / max_value * 255.0;
}

double cover_score(const std::vector<uint8_t>& frame, int width, int height) {
    const int pixel_count = width * height;
    std::vector<double> gray(pixel_count);
    double mean = 0.0;
    double saturation_sum = 0.0;
    for (int pixel = 0; pixel < pixel_count; ++pixel) {
        gray[pixel] = gray_at(frame, pixel);
        mean += gray[pixel];
        const int offset = pixel * 3;
        saturation_sum += saturation_for_rgb(frame[offset], frame[offset + 1], frame[offset + 2]);
    }
    mean /= std::max(1, pixel_count);

    double variance = 0.0;
    for (double value : gray) {
        const double delta = value - mean;
        variance += delta * delta;
    }
    const double contrast = std::sqrt(variance / std::max(1, pixel_count));

    double sharpness_sum = 0.0;
    int sharpness_count = 0;
    for (int y = 1; y + 1 < height; ++y) {
        for (int x = 1; x + 1 < width; ++x) {
            const int idx = y * width + x;
            const double laplacian =
                -4.0 * gray[idx]
                + gray[idx - 1]
                + gray[idx + 1]
                + gray[idx - width]
                + gray[idx + width];
            sharpness_sum += laplacian * laplacian;
            ++sharpness_count;
        }
    }

    const double saturation = saturation_sum / std::max(1, pixel_count);
    const double exposure = std::max(0.0, 1.0 - std::abs(mean - 122.0) / 122.0) * 18.0;
    return std::min(24.0, contrast / 3.8)
        + std::min(20.0, saturation / 8.5)
        + std::min(18.0, (sharpness_sum / std::max(1, sharpness_count)) / 140.0)
        + exposure;
}

}  // namespace

int main(int argc, char** argv) {
    const int width = parse_int_arg(argc, argv, "--width", 320);
    const int height = parse_int_arg(argc, argv, "--height", 180);
    const int frame_bytes = width * height * 3;
    if (frame_bytes <= 0) {
        return 2;
    }

    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    std::vector<uint8_t> frame(frame_bytes);
    int index = 0;
    int best_index = -1;
    double best_score = -1.0;
    while (true) {
        std::cin.read(reinterpret_cast<char*>(frame.data()), frame_bytes);
        if (std::cin.gcount() != frame_bytes) {
            break;
        }
        const double score = cover_score(frame, width, height);
        if (score > best_score) {
            best_score = score;
            best_index = index;
        }
        ++index;
    }

    if (best_index < 0) {
        return 1;
    }
    std::cout << "{\"index\":" << best_index << ",\"score\":" << best_score << "}\n";
    return 0;
}
