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

struct FrameMetrics {
    double motion = 0.0;
    double scene = 0.0;
    double sharpness = 0.0;
    double contrast = 0.0;
    double saturation = 0.0;
    double exposure = 0.0;
    double score = 0.0;
};

double clamp_double(double value, double minimum, double maximum) {
    return std::max(minimum, std::min(maximum, value));
}

double gray_at(const std::vector<uint8_t>& frame, int pixel) {
    const int offset = pixel * 3;
    return frame[offset] * 0.299 + frame[offset + 1] * 0.587 + frame[offset + 2] * 0.114;
}

std::vector<double> gray_values(const std::vector<uint8_t>& frame, int pixel_count) {
    std::vector<double> gray(pixel_count);
    for (int pixel = 0; pixel < pixel_count; ++pixel) {
        gray[pixel] = gray_at(frame, pixel);
    }
    return gray;
}

std::vector<double> color_histogram(const std::vector<uint8_t>& frame, int pixel_count) {
    std::vector<double> hist(512, 0.0);
    for (int pixel = 0; pixel < pixel_count; ++pixel) {
        const int offset = pixel * 3;
        const int r = frame[offset] / 32;
        const int g = frame[offset + 1] / 32;
        const int b = frame[offset + 2] / 32;
        hist[(r * 8 + g) * 8 + b] += 1.0;
    }
    const double denom = std::max(1, pixel_count);
    for (double& value : hist) {
        value /= denom;
    }
    return hist;
}

double histogram_distance(const std::vector<double>& a, const std::vector<double>& b) {
    if (a.empty() || b.empty() || a.size() != b.size()) {
        return 0.0;
    }
    double sum = 0.0;
    for (size_t index = 0; index < a.size(); ++index) {
        const double root_a = std::sqrt(std::max(0.0, a[index]));
        const double root_b = std::sqrt(std::max(0.0, b[index]));
        const double delta = root_a - root_b;
        sum += delta * delta;
    }
    return std::sqrt(sum) / std::sqrt(2.0);
}

double saturation_for_rgb(uint8_t r, uint8_t g, uint8_t b) {
    const double max_value = std::max({static_cast<double>(r), static_cast<double>(g), static_cast<double>(b)});
    const double min_value = std::min({static_cast<double>(r), static_cast<double>(g), static_cast<double>(b)});
    if (max_value <= 0.0) {
        return 0.0;
    }
    return (max_value - min_value) / max_value * 255.0;
}

FrameMetrics analyze_frame(
    const std::vector<uint8_t>& frame,
    const std::vector<double>* previous_gray,
    const std::vector<double>* previous_hist,
    int width,
    int height
) {
    const int pixel_count = width * height;
    const std::vector<double> gray = gray_values(frame, pixel_count);
    const std::vector<double> hist = color_histogram(frame, pixel_count);

    double mean = 0.0;
    double saturation_sum = 0.0;
    for (int pixel = 0; pixel < pixel_count; ++pixel) {
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

    double motion = 0.0;
    if (previous_gray && previous_gray->size() == gray.size()) {
        for (int pixel = 0; pixel < pixel_count; ++pixel) {
            motion += std::abs(gray[pixel] - (*previous_gray)[pixel]);
        }
        motion /= std::max(1, pixel_count);
    }

    const double scene = previous_hist ? histogram_distance(hist, *previous_hist) : 0.0;
    const double exposure = std::max(0.0, 1.0 - std::abs(mean - 118.0) / 118.0) * 6.0;
    const double saturation = saturation_sum / std::max(1, pixel_count);
    const double contrast_score = std::min(10.0, contrast / 6.0);
    const double saturation_score = std::min(8.0, saturation / 22.0);
    const double sharpness_score = std::min(12.0, (sharpness_sum / std::max(1, sharpness_count)) / 90.0);
    const double dull_penalty = (contrast < 9.0 && saturation < 18.0) ? 5.0 : 0.0;
    const double blown_penalty = (mean < 18.0 || mean > 238.0) ? 4.0 : 0.0;

    FrameMetrics metrics;
    metrics.motion = motion;
    metrics.scene = std::min(22.0, std::max(0.0, scene) * 36.0);
    metrics.sharpness = sharpness_score;
    metrics.contrast = contrast;
    metrics.saturation = saturation;
    metrics.exposure = exposure;
    const double visual_interest = std::max(0.0, contrast_score + saturation_score + exposure - dull_penalty - blown_penalty);
    metrics.score = std::min(32.0, motion) + metrics.scene + sharpness_score + visual_interest;
    return metrics;
}

void print_json(int index, const FrameMetrics& metrics) {
    std::cout
        << "{\"index\":" << index
        << ",\"motion\":" << metrics.motion
        << ",\"scene\":" << metrics.scene
        << ",\"sharpness\":" << metrics.sharpness
        << ",\"contrast\":" << metrics.contrast
        << ",\"saturation\":" << metrics.saturation
        << ",\"exposure\":" << metrics.exposure
        << ",\"score\":" << metrics.score
        << "}\n";
}

}  // namespace

int main(int argc, char** argv) {
    const int width = parse_int_arg(argc, argv, "--width", 160);
    const int height = parse_int_arg(argc, argv, "--height", 90);
    const int frame_bytes = width * height * 3;
    if (frame_bytes <= 0) {
        return 2;
    }

    std::ios::sync_with_stdio(false);
    std::cin.tie(nullptr);

    std::vector<uint8_t> frame(frame_bytes);
    std::vector<double> previous_gray;
    std::vector<double> previous_hist;
    int index = 0;
    while (true) {
        std::cin.read(reinterpret_cast<char*>(frame.data()), frame_bytes);
        if (std::cin.gcount() != frame_bytes) {
            break;
        }
        const FrameMetrics metrics = analyze_frame(
            frame,
            previous_gray.empty() ? nullptr : &previous_gray,
            previous_hist.empty() ? nullptr : &previous_hist,
            width,
            height
        );
        print_json(index, metrics);
        previous_gray = gray_values(frame, width * height);
        previous_hist = color_histogram(frame, width * height);
        ++index;
    }
    return 0;
}
