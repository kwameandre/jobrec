import streamlit as st
import PyPDF2
import docx
import io
import requests
import os
import json
import pandas as pd
import time
import anthropic
from typing import List, Dict, Any

# Import the job search function
from jobspy import scrape_jobs

# Set page configuration
st.set_page_config(
    page_title="AI Resume Job Matcher",
    page_icon="📄",
    layout="wide"
)

ANTHROPIC_API_KEY = st.secrets["anthropic"]
# Function to read PDF files
# Function to read PDF files
def read_pdf(file):
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file.getvalue()))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        st.error(f"Error reading PDF file: {str(e)}")
        return None

# Function to read DOCX files
def read_docx(file):
    try:
        doc = docx.Document(io.BytesIO(file.getvalue()))
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text
    except Exception as e:
        st.error(f"Error reading DOCX file: {str(e)}")
        return None

# Function to read TXT files
def read_txt(file):
    try:
        text = file.getvalue().decode("utf-8")
        return text
    except Exception as e:
        st.error(f"Error reading TXT file: {str(e)}")
        return None

# Function to extract resume text based on file type
def extract_resume_text(file):
    try:
        file_extension = file.name.split('.')[-1].lower()
        
        if file_extension == 'pdf':
            return read_pdf(file)
        elif file_extension == 'docx':
            return read_docx(file)
        elif file_extension == 'txt':
            return read_txt(file)
        else:
            st.error(f"Unsupported file format: {file_extension}")
            return None
    except Exception as e:
        st.error(f"Error processing file: {str(e)}")
        return None

# Function to get jobs using jobspy
# def get_jobs(search_term, location=None, experience_level=None):
#     try:
#         full_search_term = f"{search_term} {experience_level}" if experience_level else search_term
#         job_results = scrape_jobs(
#             site_name=["indeed", "LinkedIn","zip_recruiter"],
#             search_term=full_search_term,
#             location=location if location else None,
#             results_wanted=50,
#             #hours_old=72,
#             country_indeed='USA'
#         )

#         st.write(f"🔍 Job search attempted: {full_search_term} in {location}")
#         st.write(f"✅ Results returned: {len(job_results)}")

#         return job_results
#     except Exception as e:
#         st.error(f"Job search error: {e}")
#         return pd.DataFrame()

def get_jobs(search_term, location=None, experience_level=None):
    """
    Fetch jobs from Remotive API.
    """
    try:
        response = requests.get("https://remotive.com/api/remote-jobs", timeout=10)
        if response.status_code != 200:
            st.error("Error fetching jobs from Remotive.")
            return pd.DataFrame()

        jobs_data = response.json().get("jobs", [])
        filtered_jobs = []

        for job in jobs_data:
            if search_term.lower() in job["title"].lower():
                # Optional: match experience level keywords
                if experience_level:
                    if experience_level.lower() not in job["title"].lower():
                        continue

                filtered_jobs.append({
                    "title": job["title"],
                    "company": job["company_name"],
                    "location": job["candidate_required_location"],
                    "description": job["description"],
                    "url": job["url"],
                    "date_posted": job["publication_date"]
                })

        return pd.DataFrame(filtered_jobs)

    except Exception as e:
        st.error(f"Job search failed: {e}")
        return pd.DataFrame()


# Function to analyze jobs with Claude API
def analyze_jobs_with_claude(resume_text, jobs_df, additional_skills=None, top_n=20):
    # Check if API key is available
    st.write(f"money")
    if not ANTHROPIC_API_KEY:
        st.error("Anthropic API key not found. Please set it in Streamlit secrets.")
        return []
        
    # Initialize Anthropic client with API key
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    # Prepare job data for Claude
    jobs_list = []
    for i, job in jobs_df.iterrows():
        if i >= 50:  # Limit to 100 jobs to avoid token limits
            break
            
        job_data = {
            "id": i,
            "title": job.get('title', 'Unknown'),
            "company": job.get('company', 'Unknown'),
            "location": job.get('location', 'Unknown'),
            "description": job.get('description', 'No description available'),
            "date_posted": str(job.get('date_posted', '')),
            "url": job.get('url', '#')
        }
        jobs_list.append(job_data)
    
    # Create the prompt for Claude
    skills_text = ", ".join(additional_skills) if additional_skills else "None specified"
    
    prompt = f"""
    I need you to analyze a resume and a list of job postings to find the best matches.

    TASK:
    1. Review the candidate's resume
    2. Evaluate each job against the candidate's qualifications and the additional skills provided
    3. Select the top 20 most suitable jobs
    4. For each selected job, assign a match score (0-100) and write a brief paragraph explaining why it's a good fit
    5. Return results as a JSON array with job_id, score, and explanation fields

    RESUME TEXT:
    {resume_text[:4000]}  # Truncating to avoid token limits
    
    ADDITIONAL SKILLS:
    {skills_text}
    
    JOB LISTINGS (first showing 100):
    {json.dumps(jobs_list[:100], indent=2)}
    
    RESPONSE FORMAT:
    Return a JSON array with objects containing:
    - job_id: The ID of the job from the provided list
    - score: A number between 0-100 representing match quality
    - explanation: A brief paragraph explaining why this job is a good match
    
    Sort the results by score in descending order and include only the top 20 matches.
    Return ONLY the JSON array with no other text or explanations.
    """
    
    # Call Claude API
    try:
        with st.spinner("Claude is analyzing job matches..."):
            response = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=4000,
                temperature=0,
                system="You are an expert resume analyzer and job matcher. Provide accurate match scores and helpful explanations for why jobs match a candidate's profile.",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract and parse the JSON response
            response_text = response.content[0].text
            
            # Find JSON content (it might be within markdown code blocks)
            import re
            json_match = re.search(r'```(?:json)?(.*?)```', response_text, re.DOTALL)
            
            if json_match:
                json_content = json_match.group(1).strip()
            else:
                json_content = response_text
                
            # Parse the JSON
            try:
                analyzed_jobs = json.loads(json_content)
                
                # Format the results
                results = []
                for job_analysis in analyzed_jobs:
                    job_id = job_analysis.get('job_id')
                    if 0 <= job_id < len(jobs_list):
                        job_info = jobs_list[job_id]
                        results.append({
                            "title": job_info["title"],
                            "company": job_info["company"],
                            "location": job_info["location"],
                            "description": job_info["description"],
                            "url": job_info["url"],
                            "match_score": job_analysis.get('score'),
                            "match_explanation": job_analysis.get('explanation')
                        })
                
                return results
                
            except json.JSONDecodeError as e:
                st.error(f"Failed to parse Claude's response as JSON: {e}")
                st.text("Raw response: " + response_text[:1000])
                return []
                
    except Exception as e:
        st.error(f"Error calling Claude API: {e}")
        return []

# Main app layout
def main():
    st.title("AI Resume Job Matcher")
    st.write("Upload your resume and get personalized job recommendations powered by Claude AI")
    
    # Create tabs for different app sections
    tab1, tab2, tab3 = st.tabs(["Upload Resume", "Review & Search", "Job Matches"])
    
    # Initialize session state variables if they don't exist
    if 'resume_text' not in st.session_state:
        st.session_state.resume_text = None
    if 'location' not in st.session_state:
        st.session_state.location = ""
    if 'additional_skills' not in st.session_state:
        st.session_state.additional_skills = []
    if 'job_level' not in st.session_state:
        st.session_state.job_level = "General"
    if 'search_term' not in st.session_state:
        st.session_state.search_term = ""
    if 'job_results' not in st.session_state:
        st.session_state.job_results = None
    if 'ranked_jobs' not in st.session_state:
        st.session_state.ranked_jobs = None
    if 'uploaded_file_name' not in st.session_state:
        st.session_state.uploaded_file_name = None
    if 'search_completed' not in st.session_state:
        st.session_state.search_completed = False
        
    with tab1:
        st.header("Upload Your Resume")
        
        uploaded_file = st.file_uploader("Choose a file (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
        
        if uploaded_file is not None:
            try:
                st.session_state.uploaded_file_name = uploaded_file.name
                with st.spinner("Extracting resume text..."):
                    resume_text = extract_resume_text(uploaded_file)
                    if resume_text:
                        st.session_state.resume_text = resume_text
                        st.success(f"Successfully processed {uploaded_file.name}")
                        
                        # Show a preview of the extracted text
                        with st.expander("Resume Text Preview"):
                            st.text_area("Extracted text", resume_text[:1000] + "..." if len(resume_text) > 1000 else resume_text, height=200, disabled=True)
                        
                        # Job preferences section
                        st.subheader("Job Preferences")
                        
                        # Search term input
                        search_term = st.text_input("Job Search Term (e.g., Software Engineer, Data Scientist)", st.session_state.search_term)
                        st.session_state.search_term = search_term
                        
                        # Location input
                        location = st.text_input("Location (City, State - e.g., Seattle, WA)", st.session_state.location)
                        st.session_state.location = location
                        
                        # Job level selection
                        job_level = st.selectbox(
                            "Job Level",
                            ["General", "Senior", "New Grad", "Internship"],
                            index=["General", "Senior", "New Grad", "Internship"].index(st.session_state.job_level)
                        )
                        st.session_state.job_level = job_level
                        
                        # Additional skills input
                        skills_input = st.text_area("Additional Skills (one per line)", 
                                                "\n".join(st.session_state.additional_skills) if st.session_state.additional_skills else "")
                        
                        if skills_input:
                            skills_list = [skill.strip() for skill in skills_input.split("\n") if skill.strip()]
                            st.session_state.additional_skills = skills_list
                        
                        st.write("Once you've entered your preferences, go to the 'Review & Search' tab.")
                    else:
                        st.error("Failed to extract text from the uploaded file. Please try a different file.")
            except Exception as e:
                st.error(f"Error processing file: {str(e)}")
                st.info("Please try uploading a different file format or check if the file is corrupted.")
        else:
            st.info("Please upload your resume to continue.")
    
    with tab2:
        st.header("Review and Start Job Search")
        
        if st.session_state.resume_text:
            st.subheader("Resume")
            with st.expander("Resume Text", expanded=False):
                st.text_area("Content", st.session_state.resume_text, height=300, disabled=True)
            
            st.subheader("Job Search Parameters")
            st.write(f"**Search Term:** {st.session_state.search_term if st.session_state.search_term else 'Not specified'}")
            st.write(f"**Location:** {st.session_state.location if st.session_state.location else 'Not specified'}")
            st.write(f"**Job Level:** {st.session_state.job_level}")
            
            st.write("**Additional Skills:**")
            if st.session_state.additional_skills:
                for skill in st.session_state.additional_skills:
                    st.write(f"- {skill}")
            else:
                st.write("No additional skills specified.")
            
            if st.button("Start Job Search"):
                if not st.session_state.search_term:
                    st.error("Please enter a job search term before starting the search.")
                else:
                    with st.spinner("Searching for jobs..."):
                        # Convert job level to experience level format for search
                        experience_level_map = {
                            "Senior": "senior",
                            "New Grad": "entry level",
                            "Internship": "internship",
                            "General": None
                        }
                        experience_level = experience_level_map.get(st.session_state.job_level)
                        
                        # Get jobs using jobspy
                        jobs_df = get_jobs(
                            search_term=st.session_state.search_term, 
                            location=st.session_state.location,
                            experience_level=experience_level
                        )
                        
                        if jobs_df.empty:
                            st.error("No jobs found. Please try different search terms or location.")
                        else:
                            st.session_state.job_results = jobs_df
                            st.success(f"Found {len(jobs_df)} job listings.")
                            
                            # Analyze jobs with Claude
                            ranked_jobs = analyze_jobs_with_claude(
                                st.session_state.resume_text,
                                jobs_df,
                                st.session_state.additional_skills
                            )
                            
                            if ranked_jobs:
                                st.session_state.ranked_jobs = ranked_jobs
                                st.session_state.search_completed = True
                                st.success("Job analysis completed! Go to the 'Job Matches' tab to see your top matches.")
                            else:
                                st.error("Failed to analyze jobs. Please check the Anthropic API key in the secrets.")
        else:
            st.info("Please upload your resume in the 'Upload Resume' tab first.")
    
    with tab3:
        st.header("Top Job Matches")
        
        if st.session_state.search_completed and st.session_state.ranked_jobs:
            st.write(f"Found {len(st.session_state.ranked_jobs)} top job matches for your profile")
            st.write(f"**Job Level:** {st.session_state.job_level}")
            
            for i, job in enumerate(st.session_state.ranked_jobs, 1):
                with st.container():
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.subheader(f"{job['title']} at {job['company']}")
                        st.write(f"**Location:** {job['location']}")
                        st.write(f"**Match Score:** {job['match_score']}%")
                        st.write("**Why this job matches your profile:**")
                        st.write(job['match_explanation'])
                    
                    with col2:
                        st.metric("Match Score", f"{job['match_score']}%")
                        st.link_button("Apply Now", job['url'], use_container_width=True)
                
                # Show job description in expandable section
                with st.expander("Show Full Job Description"):
                    st.write(job['description'])
                
                st.divider()
                
            if st.button("Start New Search"):
                st.session_state.search_completed = False
                st.session_state.job_results = None
                st.session_state.ranked_jobs = None
                st.session_state.uploaded_file_name = None
                # Don't reset resume_text, search_term and location to improve user experience
                st.experimental_rerun()
                
        elif st.session_state.resume_text:
            st.info("Complete the job search in the 'Review & Search' tab to see matching jobs here.")
        else:
            st.info("Upload your resume and complete the search to see job matches.")

    # Add footer with disclaimer
    st.divider()
    st.caption("This application uses Claude AI to analyze resumes and job listings. Job data is fetched in real-time from Indeed and LinkedIn.")

if __name__ == "__main__":
    main()
