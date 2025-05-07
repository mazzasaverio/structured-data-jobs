import requests
import time
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# Load variables from .env file
load_dotenv()

# Get API key from environment
api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    raise ValueError(
        "No API key found. Please check your .env file contains GOOGLE_API_KEY=your_key_here"
    )

# Output folder
output_folder = "milan_specific_companies"
batch_size = 20
version = datetime.now().strftime("%Y%m%d_%H%M%S")  # Add timestamp for versioning


def search_specific_companies():
    # List of specific companies to search for
    target_companies = [
        {"name": "Google", "keywords": ["Google", "Google Italy", "Google Milano"]},
        {
            "name": "Satispay",
            "keywords": ["Satispay", "Satispay Italy", "Satispay Milano"],
        },
    ]

    all_results = {}

    for company in target_companies:
        company_name = company["name"]
        print(f"\n{'='*50}")
        print(f"Searching for {company_name} in Milan")
        print(f"{'='*50}")

        company_results = []

        for keyword in company["keywords"]:
            try:
                print(f"\nSearching with keyword: '{keyword}'...")

                # Use text search to find the company
                url = f"https://maps.googleapis.com/maps/api/place/textsearch/json?query={keyword.replace(' ', '+')}+in+Milan&key={api_key}"

                print(f"Making API request...")
                response = requests.get(url)
                data = response.json()

                if "error_message" in data:
                    print(f"API Error: {data['error_message']}")
                    continue

                if "results" in data and data["results"]:
                    results_count = len(data["results"])
                    print(f"Found {results_count} results for '{keyword}'")

                    for place in data["results"]:
                        try:
                            # Skip if we already have this place
                            if any(
                                r["name"] == place.get("name", "")
                                for r in company_results
                            ):
                                print(f"Skipping duplicate: {place.get('name', '')}")
                                continue

                            # Get detailed information for the place
                            details_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place['place_id']}&fields=name,formatted_address,website,international_phone_number,rating,user_ratings_total,opening_hours,geometry&key={api_key}"
                            details_response = requests.get(details_url)
                            details_data = details_response.json()

                            if "result" in details_data:
                                result = details_data["result"]

                                # Gather detailed information
                                business = {
                                    "name": place.get("name", ""),
                                    "address": place.get("formatted_address", ""),
                                    "website": result.get("website", "N/A"),
                                    "phone": result.get(
                                        "international_phone_number", "N/A"
                                    ),
                                    "rating": result.get("rating", "N/A"),
                                    "total_ratings": result.get(
                                        "user_ratings_total", "N/A"
                                    ),
                                    "location": result.get("geometry", {}).get(
                                        "location", {}
                                    ),
                                    "search_keyword": keyword,
                                    "details_data": details_data,
                                }

                                # Add opening hours if available
                                if "opening_hours" in result:
                                    business["opening_hours"] = result[
                                        "opening_hours"
                                    ].get("weekday_text", [])

                                company_results.append(business)
                                print(f"Added: {place.get('name', '')}")

                            time.sleep(0.5)  # Delay to avoid rate limits
                        except Exception as e:
                            print(
                                f"Error processing place {place.get('name', '')}: {e}"
                            )
                else:
                    print(f"No results found for '{keyword}'")

            except Exception as e:
                print(f"Error searching for '{keyword}': {e}")

        # Save this company's results
        all_results[company_name] = company_results
        print(
            f"\nCompleted search for {company_name}. Found {len(company_results)} locations."
        )

        # Save results for this company
        save_company_results(company_name, company_results)

    return all_results


def save_company_results(company_name, results):
    # Create the output folder if it doesn't exist
    Path(output_folder).mkdir(parents=True, exist_ok=True)

    # Save results for this company
    filename = f"{output_folder}/{company_name.lower()}_milan_locations_v{version}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

    print(f"Saved {len(results)} {company_name} locations to {filename}")
    return filename


def save_combined_results(all_results):
    # Create combined results file
    combined_file = f"{output_folder}/all_companies_v{version}.json"

    with open(combined_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=4)

    # Create summary file
    summary_file = f"{output_folder}/summary_v{version}.json"

    summary = {
        "version": version,
        "search_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "companies": {},
    }

    total_locations = 0
    for company, results in all_results.items():
        summary["companies"][company] = {
            "total_locations": len(results),
            "file": f"{company.lower()}_milan_locations_v{version}.json",
        }
        total_locations += len(results)

    summary["total_locations"] = total_locations

    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=4)

    return combined_file, summary_file


def main():
    print("Starting search for specific companies in Milan...")
    print(f"Version: {version}")

    # Search for specific companies
    all_results = search_specific_companies()

    # Save combined results and summary
    combined_file, summary_file = save_combined_results(all_results)

    # Print summary
    print("\n\n" + "=" * 60)
    print(f"SEARCH COMPLETE - RESULTS SUMMARY")
    print("=" * 60)

    total_locations = sum(len(results) for results in all_results.values())
    print(f"Total locations found: {total_locations}")

    print("\nBreakdown by company:")
    for company, results in all_results.items():
        print(f"  {company}: {len(results)} locations")

    print(f"\nData saved in the '{output_folder}' folder")
    print(f"- Individual company files saved separately")
    print(f"- Combined results: {combined_file}")
    print(f"- Summary file: {summary_file}")
    print(f"- Version: {version}")


if __name__ == "__main__":
    main()
