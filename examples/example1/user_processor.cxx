// example1/user_processor.cxx
#include <stdio.h>
#include <string>
#include <vector>

int process_user_data(std::vector<std::string> names, std::vector<int> scores,
                      std::string targetName) {
  int total_score = 0;
  int user_count = 0;

  for (int i = 0; i < names.size(); i++) {
    if (names[i] == targetName) {
      user_count++;
      total_score += scores[i];
    }
  }

  int *average_score = new int; // Memory leak and unnecessary pointer use
  if (user_count > 0) {
    *average_score = total_score / user_count;
  } else {
    *average_score = 0;
  }

  printf("Found %d users with name %s\n", user_count, targetName.c_str());
  return *average_score;
}
