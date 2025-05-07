import requests
import time
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from collections import Counter
from datetime import datetime

# Load variables from .env file
load_dotenv()

# Get API key from environment
api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    raise ValueError(
        "No API key found. Please check your .env file contains GOOGLE_API_KEY=your_key_here"
    )

# Milan city center coordinates
milan_lat = 45.4642
milan_lng = 9.1900
output_folder = "milan_software_companies"
batch_size = 20  # Changed to 20 as requested
version = datetime.now().strftime("%Y%m%d_%H%M%S")  # Add timestamp for versioning


def search_software_companies():
    businesses = []
    total_processed = 0
    files_created = []

    # Different keyword searches for software companies
    software_keywords = [
        "software company",
        "software development",
        "tech company",
        "IT company",
        "digital agency",
        "web development",
        "app development",
        "software house",
        "startup tecnologica",
        "azienda informatica",  # Italian keyword for IT company
    ]

    for keyword in software_keywords:
        try:
            page_token = None
            first_request = True
            keyword_count = 0

            print(f"\nSearching for '{keyword}' in Milan...")

            while first_request or page_token:
                first_request = False

                if page_token:
                    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?pagetoken={page_token}&key={api_key}"
                else:
                    # Use text search specifically for the keyword
                    url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={keyword.replace(' ', '+')}+in+Milan&key={api_key}"

                print(f"Making request for '{keyword}'...")
                response = requests.get(url)
                data = response.json()

                if "error_message" in data:
                    print(f"API Error: {data['error_message']}")
                    break

                if "results" in data and data["results"]:
                    results_count = len(data["results"])
                    keyword_count += results_count
                    print(f"Found {results_count} results for '{keyword}' in this page")

                    for place in data["results"]:
                        try:
                            # Check if we already have this place
                            if any(
                                b["name"] == place.get("name", "") for b in businesses
                            ):
                                print(f"Skipping duplicate: {place.get('name', '')}")
                                continue

                            details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place['place_id']}&fields=name,formatted_address,website,international_phone_number&key={api_key}"
                            details_response = requests.get(details_url)
                            details_data = details_response.json()

                            if "result" in details_data:
                                result = details_data["result"]
                                business = {
                                    "name": place.get("name", ""),
                                    "address": place.get("formatted_address", ""),
                                    "website": result.get("website", "N/A"),
                                    "phone": result.get(
                                        "international_phone_number", "N/A"
                                    ),
                                    "business_type": "software_company",
                                    "search_keyword": keyword,
                                }
                                businesses.append(business)
                                total_processed += 1
                                print(f"Added: {place.get('name', '')}")

                                # Save every 20 results
                                if total_processed % batch_size == 0:
                                    batch_files = save_current_batch(
                                        businesses,
                                        output_folder,
                                        total_processed,
                                        version,
                                    )
                                    files_created.extend(batch_files)
                                    print(
                                        f"Saved batch with {batch_size} businesses. Total processed: {total_processed}"
                                    )

                            time.sleep(0.2)  # Small delay to avoid rate limits
                        except Exception as e:
                            print(
                                f"Error processing place {place.get('name', '')}: {e}"
                            )
                else:
                    print(f"No results found for '{keyword}' in this page")

                page_token = data.get("next_page_token")

                if page_token:
                    print("Waiting before next request...")
                    time.sleep(2)

            print(f"Total results for '{keyword}': {keyword_count}")

        except Exception as e:
            print(f"Error searching for '{keyword}': {e}")

    # Save any remaining businesses that didn't make a complete batch
    if total_processed % batch_size != 0:
        remaining_count = total_processed % batch_size
        print(f"Saving final batch with {remaining_count} businesses...")
        batch_files = save_current_batch(
            businesses[-remaining_count:], output_folder, total_processed, version
        )
        files_created.extend(batch_files)

    print(f"Total software companies found: {len(businesses)}")
    return businesses, files_created


def save_current_batch(businesses, folder_path, total_count, version):
    # Create the output folder if it doesn't exist
    Path(folder_path).mkdir(parents=True, exist_ok=True)

    batch_num = total_count // batch_size
    filename = (
        f"{folder_path}/milan_software_companies_v{version}_batch_{batch_num}.json"
    )

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(businesses[-batch_size:], f, ensure_ascii=False, indent=4)

    return [filename]


def save_final_summary(businesses, folder_path, files_created, version):
    # Create a summary file with counts by keyword
    keyword_counts = Counter([b["search_keyword"] for b in businesses])
    summary_filename = f"{folder_path}/summary_v{version}.json"

    with open(summary_filename, "w", encoding="utf-8") as f:
        summary = {
            "version": version,
            "total_software_companies": len(businesses),
            "counts_by_keyword": dict(keyword_counts.most_common()),
            "batch_files": files_created,
        }
        json.dump(summary, f, ensure_ascii=False, indent=4)

    # Also save a single combined file with all businesses
    all_filename = f"{folder_path}/all_software_companies_v{version}.json"
    with open(all_filename, "w", encoding="utf-8") as f:
        json.dump(businesses, f, ensure_ascii=False, indent=4)

    return [summary_filename, all_filename]


def main():
    print("Starting to retrieve software companies in Milan...")
    print(f"Version: {version}")
    print(f"Results will be saved in batches of {batch_size}")

    # Search for software companies using various keywords
    software_companies, batch_files = search_software_companies()

    # Save final summary and complete dataset
    summary_files = save_final_summary(
        software_companies, output_folder, batch_files, version
    )

    # Print summary
    print("\n\n" + "=" * 60)
    print(f"SEARCH COMPLETE - RESULTS SUMMARY")
    print("=" * 60)
    print(f"Version: {version}")
    print(f"Total software companies found: {len(software_companies)}")

    # Print counts by keyword
    keyword_counts = Counter([b["search_keyword"] for b in software_companies])
    print("\nBreakdown by search keyword:")
    for keyword, count in keyword_counts.most_common():
        print(f"  '{keyword}': {count}")

    print(f"\nData saved in the '{output_folder}' folder")
    print(f"- Batch files: {len(batch_files)}")
    print(f"- Summary file: {summary_files[0]}")
    print(f"- Complete data: {summary_files[1]}")
    print(f"- Version: {version}")


if __name__ == "__main__":
    main()
