
@app.post("/scrape")
async def scrape_jobs(db: Session = Depends(get_db)):
    url = "https://remoteok.com/api"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    data = response.json()

    jobs_data = data[1:]

    added_count = 0
    skipped_count = 0

    for job in jobs_data[:20]:
        source_id = str(job.get("id"))
        title = job.get("position", "Unknown")
        company = job.get("company", "Unknown")
        job_url = job.get("url", "")
        
        existing = db.query(JobModel).filter(JobModel.source_id == source_id).first()

        if existing:
            skipped_count += 1
            continue

        new_job = JobModel(
            source_id=source_id,
            title=title,
            company=company,
            salary=0,
            url=job_url
        )
        db.add(new_job)
        added_count += 1

    db.commit()
    return {
        "message": f"{added_count} new jobs added, {skipped_count} duplicates skipped"
    }