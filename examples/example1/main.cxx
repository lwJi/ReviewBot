// example1/main.cxx
#include "user_processor.cpp" // Major anti-pattern: including a .cpp file.
#include "utils.hpp"
#include <iostream>
#include <vector>

int main() {
  std::vector<std::string> user_names = {"Alice", "Bob", "Charlie", "Alice"};
  std::vector<int> user_scores = {88, 92, 76, 95};
  std::string target = "Alice";

  int avg = process_user_data(user_names, user_scores, target);

  if (avg > 0) {
    std::cout << "Average score for " << target << " is: " << avg << std::endl;
  } else {
    logError("Could not calculate average score.");
    // Relies on global state, which makes code hard to reason about.
    std::cout << "An error occurred: " << last_error_message << std::endl;
  }

  return 0;
}
