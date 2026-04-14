#!/usr/bin/env python
# Script to fix jobs.py

with open('./backend/routers/jobs.py', 'r') as f:
    content = f.read()

# Replace the return statement
old_code = '''    background_tasks.add_task(run_video_pipeline_job, request.session_id, request.video_path)
    return job_store[request.session_id]'''

new_code = '''    background_tasks.add_task(run_video_pipeline_job, request.session_id, request.video_path)
    job_response = job_store[request.session_id]
    job_response["session_id"] = request.session_id
    print(f"📤 JOB RESPONSE: {job_response}")
    return job_response'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('./backend/routers/jobs.py', 'w') as f:
        f.write(content)
    print("✅ Updated /jobs/start endpoint to include session_id")
else:
    print("❌ Could not find the code to replace")
