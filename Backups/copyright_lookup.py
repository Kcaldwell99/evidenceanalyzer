from urllib.parse import urlencode


def build_copyright_search_link(
    title: str = "",
    author: str = "",
    claimant: str = "",
    registration_number: str = "",
    year: str = "",
) -> str:
    """
    Builds a public-record search URL for the U.S. Copyright Office CPRS site.
    This does not verify ownership; it only helps the user search public records.
    """

    base_url = "https://publicrecords.copyright.gov/search"

    params = {}

    if title.strip():
        params["title"] = title.strip()

    if author.strip():
        params["author"] = author.strip()

    if claimant.strip():
        params["claimant"] = claimant.strip()

    if registration_number.strip():
        params["registrationNumber"] = registration_number.strip()

    if year.strip():
        params["year"] = year.strip()

    if not params:
        return base_url

    return f"{base_url}?{urlencode(params)}"