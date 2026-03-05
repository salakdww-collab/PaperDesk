from app.services.metadata_service import extract_metadata_candidate


def test_extract_metadata_prefers_valid_pdf_title():
    candidate = extract_metadata_candidate(
        filename="paper.pdf",
        first_page_text="Fallback title line",
        pdf_title="A Better PDF Title",
        pdf_subject=None,
    )

    assert candidate.title == "A Better PDF Title"


def test_extract_metadata_joins_multiline_title_until_abstract():
    candidate = extract_metadata_candidate(
        filename="Smith_2024_Attention_Is_All_You_Need.pdf",
        first_page_text=(
            "Long Title Part One\n"
            "Part Two of the Same Title\n"
            "Abstract\n"
            "This paper proposes ... DOI: 10.1000/xyz123"
        ),
        pdf_title="Untitled",
        pdf_subject=None,
    )

    assert candidate.title == "Long Title Part One Part Two of the Same Title"
    assert candidate.year == 2024
    assert candidate.doi == "10.1000/xyz123"
    assert candidate.abstract is not None
    assert "This paper proposes" in candidate.abstract


def test_extract_metadata_extracts_abstract_section_only():
    candidate = extract_metadata_candidate(
        filename="Paper.pdf",
        first_page_text=(
            "A very good title\n"
            "Abstract\n"
            "This is the real abstract content that should be captured.\n"
            "Keywords: LLM, IR\n"
            "1 Introduction\n"
            "This part should not be included."
        ),
        pdf_title=None,
        pdf_subject=None,
    )

    assert candidate.abstract is not None
    assert "real abstract content" in candidate.abstract
    assert "Introduction" not in candidate.abstract


def test_extract_metadata_skips_author_lines_and_fallbacks_to_filename():
    candidate = extract_metadata_candidate(
        filename="Useful_Long_Title_For_Paper_2025.pdf",
        first_page_text="Alice Bob, Carol Dave\ncarol@uni.edu\nDepartment of Computer Science",
        pdf_title="document",
        pdf_subject=None,
    )

    assert candidate.title == "Useful Long Title For Paper 2025"
    assert candidate.year == 2025


def test_extract_metadata_skips_front_matter_when_extracting_title():
    candidate = extract_metadata_candidate(
        filename="equivalence.pdf",
        first_page_text=(
            "arXiv:1207.6076v3 [stat.ME] 12 Nov 2013\n"
            "The Annals of Statistics\n"
            "2013, Vol. 41, No. 5, 2263-2291\n"
            "DOI: 10.1214/13-AOS1140\n"
            "EQUIVALENCE OF DISTANCE-BASED AND RKHS-BASED\n"
            "STATISTICS IN HYPOTHESIS TESTING\n"
            "By Dino Sejdinovic, Bharath Sriperumbudur, Arthur Gretton and Kenji Fukumizu\n"
        ),
        pdf_title="document",
        pdf_subject=None,
    )

    assert candidate.title == "EQUIVALENCE OF DISTANCE-BASED AND RKHS-BASED STATISTICS IN HYPOTHESIS TESTING"


def test_extract_metadata_fallback_abstract_avoids_header_and_author_lines():
    candidate = extract_metadata_candidate(
        filename="energy.pdf",
        first_page_text=(
            "Advanced Review\n"
            "Energy distance\n"
            "Maria L. Rizzo and Gabor J. Szekely\n"
            "Energy distance is a metric that measures the distance between distributions.\n"
            "It characterizes equality of distributions and supports inference.\n"
            "Keywords: distance covariance\n"
            "INTRODUCTION\n"
        ),
        pdf_title="document",
        pdf_subject=None,
    )

    assert candidate.abstract is not None
    assert candidate.abstract.startswith("Energy distance is a metric")
    assert "Advanced Review" not in candidate.abstract
    assert "Maria L. Rizzo" not in candidate.abstract
