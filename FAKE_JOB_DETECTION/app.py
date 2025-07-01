from flask import Flask, request, render_template
import joblib
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
from urllib.parse import urlparse
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)

# Load the trained model
try:
    model = joblib.load('fake_3.pkl')
except Exception as e:
    print(f"Error loading model: {e}")
    model = None

# Common fake job indicators (case insensitive)
FAKE_INDICATORS = [
    r'work from home', r'immediate (joining|hiring)', r'earn (money|€|\$|£)',
    r'no experience needed', r'(whatsapp|telegram) (contact|number)',
    r'part[- ]?time', r'flexible (hours|timing)', r'no interview',
    r'urgent hiring', r'data entry', r'no (qualification|education) needed',
    r'work anywhere', r'start earning today', r'100% (remote|work from home)',
    r'no fees', r'quick money', r'no age limit', r'confidential company',
    r'immediate start'
]

def extract_domain(url):
    parsed = urlparse(url)
    return parsed.netloc.lower()

def clean_text(text):
    if not text:
        return ""
    text = str(text).lower()
    text = re.sub(r'[^a-zA-Z0-9\s\-.,!?]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_likely_fake(text):
    if not text:
        return False
    text = clean_text(text)
    for pattern in FAKE_INDICATORS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False

def scrape_linkedin(soup):
    job_details = {
        "company_name": "Unknown", "job_title": "Unknown", "job_description": "",
        "salary": "Not Specified", "experience": "Not Specified",
        "qualification": "Not Specified", "skills": "Not Specified"
    }
    try:
        title_elem = soup.find('h1', class_='top-card-layout__title')
        if title_elem:
            job_details['job_title'] = title_elem.get_text(strip=True)
        company_elem = soup.find('a', class_='topcard__org-name-link')
        if company_elem:
            job_details['company_name'] = company_elem.get_text(strip=True)
        desc_elem = soup.find('div', class_='description__text')
        if desc_elem:
            job_details['job_description'] = desc_elem.get_text(strip=True)
        criteria = soup.find_all('li', class_='description__job-criteria-item')
        for item in criteria:
            label = item.find('h3', class_='description__job-criteria-subheader')
            value = item.find('span', class_='description__job-criteria-text')
            if label and value:
                label_text = clean_text(label.get_text(strip=True))
                if 'experience' in label_text:
                    job_details['experience'] = value.get_text(strip=True)
                elif 'employment type' in label_text:
                    job_details['employment_type'] = value.get_text(strip=True)
        return job_details
    except Exception as e:
        print(f"LinkedIn scraping error: {e}")
        return job_details

def scrape_indeed(soup):
    job_details = {
        "company_name": "Unknown", "job_title": "Unknown", "job_description": "",
        "salary": "Not Specified", "experience": "Not Specified",
        "qualification": "Not Specified", "skills": "Not Specified"
    }
    try:
        title_elem = soup.find('h1', class_='jobsearch-JobInfoHeader-title')
        if title_elem:
            job_details['job_title'] = title_elem.get_text(strip=True)
        company_elem = soup.find('div', class_='jobsearch-InlineCompanyRating')
        if company_elem:
            company_name = company_elem.find('a')
            if company_name:
                job_details['company_name'] = company_name.get_text(strip=True)
        desc_elem = soup.find('div', id='jobDescriptionText')
        if desc_elem:
            job_details['job_description'] = desc_elem.get_text(strip=True)
        salary_elem = soup.find('div', id='salaryInfoAndJobType')
        if salary_elem:
            job_details['salary'] = salary_elem.get_text(strip=True)
        return job_details
    except Exception as e:
        print(f"Indeed scraping error: {e}")
        return job_details

def scrape_generic(soup):
    job_details = {
        "company_name": "Unknown", "job_title": "Unknown", "job_description": "",
        "salary": "Not Specified", "experience": "Not Specified",
        "qualification": "Not Specified", "skills": "Not Specified"
    }
    try:
        title_elem = soup.find(['h1', 'h2'])
        if title_elem:
            job_details['job_title'] = title_elem.get_text(strip=True)
        company_elems = soup.find_all(['span', 'div', 'p'], string=re.compile(r'company|employer|organization', re.I))
        for elem in company_elems:
            text = elem.get_text(strip=True)
            if len(text) > 3 and text.lower() not in ['company', 'employer']:
                job_details['company_name'] = text
                break
        desc_elem = soup.find('div', class_=re.compile(r'description|content|details', re.I)) or \
                   soup.find('section', id=re.compile(r'description|content', re.I))
        if desc_elem:
            job_details['job_description'] = desc_elem.get_text(strip=True)
        if job_details['job_description']:
            skills_section = re.search(r'(required|key|essential)\s*(skills|qualifications):?(.*?)(?=\n\n|\n\w|$)',
                                       job_details['job_description'], re.I)
            if skills_section:
                job_details['skills'] = skills_section.group(3).strip()
        return job_details
    except Exception as e:
        print(f"Generic scraping error: {e}")
        return job_details

def scrape_job_details(job_link):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        }
        response = requests.get(job_link, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        domain = extract_domain(job_link)
        if 'linkedin.com' in domain:
            job_details = scrape_linkedin(soup)
        elif 'indeed.com' in domain:
            job_details = scrape_indeed(soup)
        else:
            job_details = scrape_generic(soup)
        job_details['job_link'] = job_link
        combined_text = f"{job_details['job_title']} {job_details['job_description']} {job_details['company_name']}"
        job_details['rule_based_fake'] = is_likely_fake(combined_text)
        return job_details
    except requests.exceptions.RequestException as e:
        return {
            "error": f"Could not fetch job details: {str(e)}",
            "job_link": job_link,
            "rule_based_fake": True
        }
    except Exception as e:
        return {
            "error": f"Error processing job details: {str(e)}",
            "job_link": job_link,
            "rule_based_fake": True
        }

def prepare_features(job_details):
    features = {
        'job_text': f"{job_details['job_title']} {job_details['job_description']} {job_details.get('skills', '')}",
        'salary': job_details.get('salary', 'Not Specified'),
        'experience': job_details.get('experience', 'Not Specified'),
        'qualification': job_details.get('qualification', 'Not Specified')
    }
    return pd.DataFrame([features])

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        input_method = request.form.get('input_method', 'link')

        if input_method == 'link':
            job_link = request.form.get('job_link', '').strip()
            if not job_link:
                return render_template('index.html', error="Please enter a job link")
            if not job_link.startswith(('http://', 'https://')):
                job_link = 'http://' + job_link
            job_details = scrape_job_details(job_link)
            if 'error' in job_details:
                return render_template('index.html', error=job_details['error'], job_link=job_link)
            if job_details.get('rule_based_fake', False):
                return render_template('result.html', result="Fake Job", job_details=job_details, confidence="High (Rule-based detection)")
        else:
            job_details = {
                "company_name": request.form.get('company_name', 'Unknown').strip(),
                "job_title": request.form.get('job_title', 'Unknown').strip(),
                "job_description": request.form.get('job_description', '').strip(),
                "salary": request.form.get('salary', 'Not Specified').strip(),
                "experience": request.form.get('experience', 'Not Specified').strip(),
                "qualification": request.form.get('qualification', 'Not Specified').strip(),
                "skills": request.form.get('skills', 'Not Specified').strip(),
                "job_link": ""
            }

            # Manual entry validation logic
            invalid = any(value.lower() in ['unknown', 'not specified', ''] 
                          for key, value in job_details.items() 
                          if key in ['company_name', 'qualification', 'skills'])
            if invalid:
                return render_template('result.html', result="Fake Job", job_details=job_details, confidence="High (Manual Rule-based)")

        if model is None:
            return render_template('result.html', result="Error", job_details=job_details, confidence="Model not loaded")
        try:
            features_df = prepare_features(job_details)
            prediction = model.predict(features_df)[0]
            probability = model.predict_proba(features_df)[0][1]
            result = "Fake Job" if prediction == 1 else "Real Job"
            confidence = f"{probability*100:.1f}%"
            return render_template('result.html', result=result, job_details=job_details, confidence=confidence)
        except Exception as e:
            print(f"Prediction error: {e}")
            return render_template('result.html', result="Error in prediction", job_details=job_details, confidence="N/A")

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
