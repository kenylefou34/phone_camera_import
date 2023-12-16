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
#define WHATSAPP_KEYWORD "WhatsApp"

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
using namespace std::filesystem;
using Path = std::filesystem::path;
using Paths = std::vector<Path>;

using MonthFiles = std::map<std::string, fs::Path>;
using YearsMonthFiles = std::map<std::string, MonthFiles>;

const std::string toLower(const std::string& data) {
  std::string lower_str;
  std::transform(data.cbegin(), data.cend(), std::back_inserter(lower_str),
                 [](const unsigned char c) { return std::tolower(c); });
  return std::move(lower_str);
}
}  // namespace fs

struct YearMonthFile {
  std::string year{"1900"};
  std::string month{"01"};
  std::string day{"01"};
  std::string ext{"ext"};
  fs::Path path{"unknown"};
  std::string status{"none"};
  fs::Path destination{"unknown"};

  bool isWhatsAppFile() {
    const auto lower_whatsapp_keyword = fs::toLower(WHATSAPP_KEYWORD);
    for (const auto& name : path) {
      const auto lower_name = fs::toLower(name.native());
      if (lower_name == lower_whatsapp_keyword) {
        return true;
      }
    }
    return false;
  }

  std::string to_string() {
    return fmt::format("{}-{}-{}: \"{}\"", year, month, day, path.native());
  }
  void print() {
    SPDLOG_INFO("{}-{}-{}: \"{}\"", year, month, day, path.native());
  }
};

using YearMonthFiles = std::vector<YearMonthFile>;

using Filters = std::vector<std::string>;
using FiltersList = std::vector<Filters>;

Filters PICTURES_FILTER{".png", ".jpg", ".jpeg", ".bmp", ".dng"};
Filters MOVIES_FILTER{".mp4", ".mkv", ".avi", ".mov", ".ogg",
                      ".m4v", ".wmv", ".3gp", ".m4a", ".webp"};
Filters EXTENSION_FILTERS;

FiltersList EXCEPTIONS_FILTER{{"WhatsApp", "Sent"},
                              {"WhatsApp", "WhatsApp Animated Gifs"},
                              {"WhatsApp", "WhatsApp Documents"},
                              {"WhatsApp", "WhatsApp Stickers"},
                              {"WhatsApp", "WhatsApp Video Notes"}};

#define DEFAULT_VIDEOS_FOLDER_NAME \
  fs::Path { "Videos" }
#define DEFAULT_PHOTOS_FOLDER_NAME \
  fs::Path { "Photos" }

std::map<std::string, std::string> MONTHS{
    {"01", "JANVIER"}, {"02", "FEVRIER"},  {"03", "MARS"},
    {"04", "AVRIL"},   {"05", "MAI"},      {"06", "JUIN"},
    {"07", "JUILLET"}, {"08", "AOUT"},     {"09", "SEPTEMBRE"},
    {"10", "OCTOBRE"}, {"11", "NOVEMBRE"}, {"12", "DECEMBRE"}};

bool isHidden(const fs::Path& source) {
  for (const auto& name : source) {
    if (name.native().starts_with(".")) {
      SPDLOG_DEBUG("Source file {} is hidden here {}", source.native(),
                   name.native());
      return true;
    }
  }
  return false;
}

bool isException(const fs::Path& source) {
  for (const auto& filter_keys : EXCEPTIONS_FILTER) {
    std::size_t count{0};
    for (const auto& keyword : filter_keys) {
      if (std::find(source.begin(), source.end(), keyword) == source.end()) {
        break;
      }
      ++count;
    }
    // This file is filtered
    if (count == filter_keys.size()) {
      SPDLOG_DEBUG("Source file {} filtered by filter list: [{}]",
                   source.native(), fmt::join(filter_keys, ","));
      return true;
    }
  }
  return false;
}

struct ReadableSizeFilter {
  std::uintmax_t size{};
  std::uintmax_t minimum_size{200 * 1024};  // 200kB

 public:
  bool isToSmall() { return size < minimum_size; }

 private:
  friend std::ostream& operator<<(std::ostream& os, ReadableSizeFilter hr) {
    int o{0};
    double mantissa = hr.size;
    for (; mantissa >= 1024.; ++o) {
      mantissa /= 1024.;
    }
    os << std::ceil(mantissa * 10.) / 10. << "BKMGTPE"[o];
    return o ? os << "B (" << hr.size << ')' : os;
  }
};

// TODO: Manage copying all type of files (movies/pictures) in different deduced
// folders (Videos/Photos)

void retrieveFiles(const fs::Path& source_folder, YearMonthFiles& files,
                   const bool use_exceptions_filter) {
  fs::Paths source_paths;
  for (auto& f : fs::directory_iterator(source_folder)) {
    if (f.path().filename().empty()) {
      continue;
    }
    // Add the file path to the list
    source_paths.push_back(f);
  }

  for (const auto& p : source_paths) {
    if (fs::is_directory(p)) {
      retrieveFiles(p, files, use_exceptions_filter);
    } else {
      // If there is extension filters - check files extensions
      if (!EXTENSION_FILTERS.empty()) {
        // Check for an existing extension
        if (!p.has_extension()) {
          continue;
        }
        // Check extension
        const auto lower_ext = fs::toLower(p.extension().native());
        // Check extension filtering
        if (std::find(EXTENSION_FILTERS.cbegin(), EXTENSION_FILTERS.cend(),
                      lower_ext) == EXTENSION_FILTERS.cend()) {
          SPDLOG_ERROR("\"{}\" is filtered out by extension ({})", p.native(),
                       lower_ext);
          continue;
        }
        // Check hidden file/folder
        if (isHidden(p)) {
          SPDLOG_ERROR("\"{}\" is hidden", p.native());
          continue;
        }
        // Check exceptions
        if (use_exceptions_filter && isException(p)) {
          SPDLOG_ERROR("\"{}\" is in exception filter", p.native());
          continue;
        }
        // Check size
        ReadableSizeFilter file_size(fs::file_size(p));
        if (file_size.isToSmall()) {
          SPDLOG_ERROR("\"{}\" is too small {}", p.native(), file_size);
          continue;
        }
      }

      const auto time = std::chrono::system_clock::to_time_t(
          std::chrono::file_clock::to_sys(fs::last_write_time(p)));
      const std::string time_format("%F");

      std::ostringstream ss;
      ss << std::put_time(std::localtime(&time), time_format.c_str());

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
  const auto no_default_final_dest =
      app.add_flag("--do-not-deduce-final-dest-folder",
                   "Without this flag we are deducing automatically deduce "
                   "last tree folder with 'Videos' or 'Photos'");

  const auto no_exceptions_filter = app.add_flag(
      "--do-not-filter-exceptions",
      "Disabling hard coded exceptions like 'WhatsApp' 'Sent' data");

  const bool use_default_final_dest = no_default_final_dest->count() == 0;
  const bool use_exceptions_filter = no_exceptions_filter->count() == 0;

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

  // Manage default final folder if we are copying only movies or only
  // pictures
  if (use_default_final_dest && !copy_all) {
    dest_folder = dest_folder / (copy_movies ? DEFAULT_VIDEOS_FOLDER_NAME
                                             : DEFAULT_PHOTOS_FOLDER_NAME);
  }

  SPDLOG_INFO("Listing files...");

  YearMonthFiles files;
  retrieveFiles(source_folder, files, use_exceptions_filter);

  SPDLOG_INFO("Copying files...");

  std::size_t file_index{0};
  auto start = clock_type::now();
  for (auto& file : files) {
    ++file_index;

    fs::Path file_dest_folder = dest_folder;
    if (file.isWhatsAppFile()) {
      file_dest_folder = file_dest_folder / WHATSAPP_KEYWORD;
    }
    file_dest_folder = file_dest_folder / file.year / file.month;

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

    SPDLOG_INFO("Copying {}/{}:\n{}\nto destination\n{}", file_index,
                files.size(), file.path, file.destination);

    std::error_code ec;
    if (remove_copied) {
      fs::rename(file.path, file.destination, ec);
    } else {
      const auto file_time = fs::last_write_time(file.path, ec);
      fs::copy_file(file.path, file.destination, ec);
      fs::last_write_time(file.destination, file_time, ec);
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
    if (ec.value() != 0) {
      SPDLOG_ERROR("Error when {} file:\n\"{}\" -> \"{}\"",
                   remove_copied ? "moving" : "copying", file.path.native(),
                   file.destination.native());
      file.status = ec.message();
    } else {
      file.status = OK_STATUS;
    }

    auto elapsed = clock_type::now() - start;
    auto ratio = file_index / static_cast<double>(files.size());

    auto seconds = chrono::duration_cast<seconds_fp>(elapsed).count();
    auto minutes = chrono::duration_cast<minutes_fp>(elapsed).count();
    auto need_minutes = seconds > 60;

    double eta{0.f};
    if (ratio > 0) {
      eta = static_cast<double>(seconds) / ratio;
    }
    auto need_minutes_eta = eta >= 60;

    SPDLOG_INFO("Status... {:.0g}{} ({:.2g}%) - ETA {:.0g}{}",
                need_minutes ? minutes : seconds, need_minutes ? "min" : "s",
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
