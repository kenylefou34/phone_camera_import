#include <assert.h>
#include <spdlog/fmt/fmt.h>
#include <spdlog/fmt/ostr.h>
#include <spdlog/sinks/basic_file_sink.h>
#include <spdlog/spdlog.h>
#include <time.h>

#include <CLI/App.hpp>
#include <CLI/Config.hpp>
#include <CLI/Formatter.hpp>
#include <boost/algorithm/string.hpp>
#include <boost/algorithm/string/predicate.hpp>
#include <boost/filesystem.hpp>
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <opencv2/highgui.hpp>
#include <opencv2/opencv.hpp>
#include <set>
#include <sstream>
#include <string_view>
#include <vector>

#define OK_STATUS "Copied"

// Get current date/time, format is YYYY-MM-DD.HH:mm:ss
const std::string currentDateTime() {
  std::time_t now = std::time(nullptr);
  std::tm tstruct = *std::localtime(&now);

  char buf[80];
  std::strftime(buf, sizeof(buf), "%Y-%m-%d_%H-%M-%S", &tstruct);

  return buf;
}

using namespace std::literals;
namespace chrono = std::chrono;
using clock_type = chrono::high_resolution_clock;
using seconds_fp = chrono::duration<double, chrono::seconds::period>;
using minutes_fp = chrono::duration<double, chrono::minutes::period>;

namespace fs {
using namespace boost::filesystem;

using Path = boost::filesystem::path;
using Paths = std::vector<Path>;

using MonthFiles = std::map<std::string, fs::Path>;
using YearsMonthFiles = std::map<std::string, MonthFiles>;
}  // namespace fs

struct YearMonthFile {
  std::string year{"1900"};
  std::string month{"01"};
  std::string day{"01"};
  std::string ext{"ext"};
  fs::Path path{"unknown"};
  std::string status{"none"};

  fs::Path destination{"unknown"};

  std::string to_string() {
    return fmt::format("{}-{}-{}: \"{}\"", year, month, day, path.native());
  }
  void print() {
    SPDLOG_INFO("{}-{}-{}: \"{}\"", year, month, day, path.native());
  }
};

using YearMonthFiles = std::vector<YearMonthFile>;

using Filters = std::vector<std::string>;

Filters PICTURES_FILTER{".png", ".jpg", ".jpeg", ".bmp", ".dng"};
Filters MOVIES_FILTER{".mp4", ".mkv", ".avi", ".mov", ".ogg",
                      ".m4v", ".wmv", ".3gp", ".m4a", ".webp"};

Filters EXTENSION_FILTERS;

std::map<std::string, std::string> MONTHS{
    {"01", "JANVIER"}, {"02", "FEVRIER"},  {"03", "MARS"},
    {"04", "AVRIL"},   {"05", "MAI"},      {"06", "JUIN"},
    {"07", "JUILLET"}, {"08", "AOUT"},     {"09", "SEPTEMBRE"},
    {"10", "OCTOBRE"}, {"11", "NOVEMBRE"}, {"12", "DECEMBRE"}};

void retrieveFiles(const fs::Path& source_folder, YearMonthFiles& files) {
  fs::Paths source_paths;
  for (auto& f : fs::directory_iterator(source_folder)) {
    if (f.path().filename_is_dot() || f.path().filename_is_dot_dot()) {
      continue;
    }
    // Add the file path to the list
    source_paths.push_back(f);
  }

  for (auto& p : source_paths) {
    if (fs::is_directory(p)) {
      retrieveFiles(p, files);
    } else {
      // If there is extension filters - check files extensions
      if (!EXTENSION_FILTERS.empty()) {
        // Check for an existing extension
        if (!p.has_extension()) {
          continue;
        }
        // Check extension
        const auto lower_ext =
            boost::algorithm::to_lower_copy(p.extension().native());

        if (std::find(EXTENSION_FILTERS.cbegin(), EXTENSION_FILTERS.cend(),
                      lower_ext) == EXTENSION_FILTERS.cend()) {
          SPDLOG_ERROR("\"{}\" is filtered out... ({})", p.native(), lower_ext);
          continue;
        }
      }

      const std::time_t elapsed_time = fs::last_write_time(p);

      const std::string time_format("%F");

      std::ostringstream ss;
      ss << std::put_time(std::localtime(&elapsed_time), time_format.c_str());

      std::string time_str(ss.str());

      auto year_str = time_str.substr(0, 4);
      auto month_str = time_str.substr(5, 2);
      auto day_str = time_str.substr(8, 2);

      files.emplace_back(
          YearMonthFile{year_str, month_str + " " + MONTHS.at(month_str),
                        day_str, p.extension().native(), p, "Listed"});
    }
  }
}

int main(int argc, char** argv) {
  SPDLOG_INFO("Hello World!");

  CLI::App app{
      "Import files from a folder to an other classifying files by last "
      "write "
      "date"};

  fs::Path source_folder, dest_folder;
  bool show_pictures = false, copy_pictures = false, copy_movies = false,
       copy_all = false, recursive_copy = false, remove_copied = false;

  auto all_option =
      app.add_flag("-a,--all", copy_all, "Copy all files")->default_val(false);
  app.add_flag("-p,--pictures", copy_pictures, "Copy pictures files")
      ->default_val(false)
      ->excludes(all_option);
  app.add_flag("-m,--movies", copy_movies, "Copy movies files")
      ->default_val(false)
      ->excludes(all_option);
  app.add_flag("--show-pictures", show_pictures, "Show pictures files")
      ->default_val(false)
      ->excludes(all_option);

  app.add_flag("-r,--recursive", recursive_copy, "Recursive source folder copy")
      ->default_val(true);
  app.add_flag("--remove-copied", remove_copied, "Remove copied files")
      ->default_val(false);

  app.add_option("-s,--source_folder", source_folder,
                 "The source folder to copy")
      ->required()
      ->check(CLI::ExistingDirectory);
  app.add_option("-d,--destination_folder", dest_folder,
                 "The destination folder to copy")
      ->required()
      ->check(CLI::ExistingDirectory);

  CLI11_PARSE(app, argc, argv);

  // Check if the source folder contains the destination folder
  if (boost::starts_with(source_folder, dest_folder)) {
    SPDLOG_ERROR(
        "Destination folder is contained in the source folder: {} -> {}",
        source_folder.native(), dest_folder.native());
    return -1;
  }
  // Check if the destination folder contains the source folder
  if (boost::starts_with(dest_folder, source_folder)) {
    SPDLOG_ERROR(
        "Source folder is contained in the destination folder: {} -> {}",
        source_folder.native(), dest_folder.native());
    return -1;
  }

  if (copy_pictures && copy_movies) {
    SPDLOG_INFO("Operation will copy pictures and movies");
    EXTENSION_FILTERS.reserve(PICTURES_FILTER.size() + MOVIES_FILTER.size());
    EXTENSION_FILTERS.insert(EXTENSION_FILTERS.end(), PICTURES_FILTER.begin(),
                             PICTURES_FILTER.end());
    EXTENSION_FILTERS.insert(EXTENSION_FILTERS.end(), MOVIES_FILTER.begin(),
                             MOVIES_FILTER.end());
  } else if (copy_pictures) {
    SPDLOG_INFO("Operation will {} pictures", remove_copied ? "move" : "copy");
    EXTENSION_FILTERS = PICTURES_FILTER;
  } else if (copy_movies) {
    SPDLOG_INFO("Operation will {} movies", remove_copied ? "move" : "copy");
    EXTENSION_FILTERS = MOVIES_FILTER;
  } else if (all_option) {
    SPDLOG_INFO("Operation will {} all files", remove_copied ? "move" : "copy");
    EXTENSION_FILTERS.clear();
  } else {
    SPDLOG_CRITICAL("Missing extension filter option or illformed options");
    return 1;
  }

  assert(fs::exists(source_folder));
  assert(fs::exists(dest_folder));

  SPDLOG_INFO("Listing files...");

  YearMonthFiles files;
  retrieveFiles(source_folder, files);

  SPDLOG_INFO("Copying files...");

  std::size_t count_copied{0};
  auto start = clock_type::now();
  for (auto& file : files) {
    ++count_copied;
    auto file_dest_folder = dest_folder / file.year / file.month;

    if (!fs::exists(file_dest_folder)) {
      if (!fs::create_directories(file_dest_folder)) {
        SPDLOG_ERROR("Unable to create the directory: \"{}\"",
                     file_dest_folder.native());
        SPDLOG_ERROR("Skipping file:\n\"{}\"", file.to_string());
        file.status = fmt::format("Unable to create directory \"{}\"",
                                  file_dest_folder.native());
        continue;
      }
    }

    auto file_dest_path = file_dest_folder / file.path.filename();

    file.destination = file_dest_path;

    if (fs::exists(file_dest_path)) {
      SPDLOG_ERROR("File already exists: \"{}\"", file_dest_path.native());
      if (fs::file_size(file_dest_path) != fs::file_size(file.path)) {
        SPDLOG_ERROR("File has different size then rename it");

        fs::Path new_path;
        std::size_t count{0};
        do {
          new_path = file_dest_path.parent_path() /
                     fs::Path(file_dest_path.stem().string() + "_" +
                              std::to_string(count++) +
                              file_dest_path.extension().string());
        } while (fs::exists(new_path));

        SPDLOG_ERROR("File renaming:\n\"{}\" -> \"{}\"",
                     file_dest_path.filename().native(),
                     new_path.filename().native());
        file.status = "Renamed";

        file_dest_path = new_path;
        // If file name for destination changed then update it
        file.destination = file_dest_path;
      } else {
        file.status = "Skipped";
        continue;
      }
    }

    SPDLOG_INFO("Copying {}/{}: {}", count_copied, files.size(), file.path);

    boost::system::error_code ec;
    if (remove_copied) {
      fs::rename(file.path, file.destination, ec);
    } else {
      fs::copy_file(file.path, file.destination, ec);
    }

    if (show_pictures && copy_pictures && !copy_all) {
      try {
        auto img_mat = cv::imread(file.destination.native());
        auto width = img_mat.cols;
        auto height = img_mat.rows;
        auto max_size = std::max(width, height);
        auto ratio = (float)640 / (float)max_size;
        cv::Mat img_resized;
        cv::resize(img_mat, img_resized,
                   cv::Size((int)(width * ratio), (int)(height * ratio)),
                   cv::INTER_LINEAR);
        cv::imshow("Preview", img_resized);
        cv::waitKey(150);
      } catch (...) {
        SPDLOG_ERROR("Error when {} file:\n\"{}\" -> \"{}\"",
                     remove_copied ? "moving" : "copying", file.path.native(),
                     file.destination.native());
        cv::waitKey();
      }
    }

    // Check error code
    if (ec.failed()) {
      SPDLOG_ERROR("Error when {} file:\n\"{}\" -> \"{}\"",
                   remove_copied ? "moving" : "copying", file.path.native(),
                   file.destination.native());
      file.status = ec.message();
    } else {
      file.status = OK_STATUS;
    }

    auto elapsed = clock_type::now() - start;
    auto ratio =
        static_cast<float>(count_copied) / static_cast<float>(files.size());

    auto seconds = chrono::duration_cast<seconds_fp>(elapsed).count();
    auto minutes = chrono::duration_cast<minutes_fp>(elapsed).count();
    auto need_minutes = seconds > 60;

    double eta{0.f};
    if (ratio > 0) {
      eta = static_cast<double>(seconds) / ratio;
    }
    auto need_minutes_eta = eta >= 60;

    SPDLOG_INFO("Status... {}{} ({}%) - ETA {}{}",
                need_minutes ? seconds : minutes, need_minutes ? "min" : "s",
                ratio * 100,
                need_minutes_eta ? eta / 60. - minutes : eta - seconds,
                need_minutes_eta ? "min" : "s");
  }

  // Write log file
  auto date_str = currentDateTime();
  std::shared_ptr<spdlog::logger> file_logger = spdlog::basic_logger_mt(
      "file_logger",
      fs::Path{dest_folder / fmt::format("copy_log_info_{}.txt", date_str)}
          .native());
  std::shared_ptr<spdlog::logger> file_error = spdlog::basic_logger_mt(
      "file_error",
      fs::Path{dest_folder / fmt::format("copy_log_error_{}.txt", date_str)}
          .native());
  for (const auto& file : files) {
    if (file.status != OK_STATUS) {
      file_error->error("\"{}\" -> \"{}\" \tstatus : \"{}\"\n",
                        file.path.native(), file.destination.native(),
                        file.status);
    } else {
      file_logger->info("\"{}\" -> \"{}\" \tstatus : \"{}\"\n",
                        file.path.native(), file.destination.native(),
                        file.status);
    }
  }
  file_logger->flush();
  file_error->flush();

  return 0;
}
