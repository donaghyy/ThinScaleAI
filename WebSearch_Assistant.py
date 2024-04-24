import os
import json
import time
import re
from openai import OpenAI
from tavily import TavilyClient
from flask import Flask, render_template, request, redirect

app = Flask(__name__)

# Initialize clients with API keys
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

assistant_prompt_instruction = """You are an Employee at ThinScale.
Your goal is to provide answers based on information from the internet knowledge base for Thinscale. 
You must tailor your responses to only include information relating to thinscale available from their web knowledge base.
You must use the provided Tavily search API function to find relevant online information. 
You should never use your own knowledge to answer questions.
If you do not know the answer, please either redirect the user to the kb.thinscale URL provided.
Always include relevant url sources in the end of your answers.
Never mention the tools you need to use t odo your job.
"""

# Function to perform a Tavily search
def tavily_search(query):
    search_result = tavily_client.get_search_context(query, search_depth="basic", max_tokens=8000, max_results=1, include_domains=["https://kb.thinscale.com"])
    return search_result

# Function to wait for a run to complete
def wait_for_run_completion(thread_id, run_id):
    while True:
        time.sleep(1)
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        print(f" - Current run status: {run.status}")
        
        if run.status in ['completed', 'failed', 'requires_action']:
            return run

# Function to handle tool output submission
def submit_tool_outputs(thread_id, run_id, tools_to_call):
    tool_output_array = []
    for tool in tools_to_call:
        output = None
        tool_call_id = tool.id
        function_name = tool.function.name
        function_args = tool.function.arguments

        if function_name == "tavily_search":
            output = tavily_search(query=json.loads(function_args)["query"])

        if output:
            tool_output_array.append({"tool_call_id": tool_call_id, "output": output})

    return client.beta.threads.runs.submit_tool_outputs(
        thread_id=thread_id,
        run_id=run_id,
        tool_outputs=tool_output_array
    )

# Function to print messages from a thread
def print_messages_from_thread(thread_id):
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    for msg in messages:
        if msg.role == "assistant":
            response = f"{msg.content[0].text.value}"
            # Format response with clickable links
            response_with_links = format_links(response)
            #print("Response with Links:", response_with_links)  # Debug print
            return response_with_links

# Function to format URLs in text as clickable links
def format_links(text):
    def repl(match):
        url = match.group(0)
        # Remove leading "(" and trailing ")."
        url = url.lstrip("(").rstrip(").")
        return f'<a href="{url}" target="_blank">{url}</a>'
    
    # Regex pattern to match URLs
    pattern = r'\(?https?://\S+\)?'
    
    # Replace URLs with clickable links
    formatted_text = re.sub(pattern, repl, text)
    return formatted_text


# Empty method to handle "End" button click and delete assistant
def end_conversation(assistant_id):
    print("Conversation ended.")

# Use the existing assistant with ID "asst_Q36A1KhKBy8Cl4zUq3qkK4gm"
assistant_id = "asst_Q36A1KhKBy8Cl4zUq3qkK4gm"
print(f"Using existing Assistant with ID: {assistant_id}")

# Create an assistant
# assistant = client.beta.assistants.create(
#     instructions=assistant_prompt_instruction,
#     model="gpt-4-1106-preview",
#     tools=[{
#         "type": "function",
#         "function": {
#             "name": "tavily_search",
#             "description": "Get information on recent events from the web.",
#             "parameters": {
#                 "type": "object",
#                 "properties": {
#                     "query": {"type": "string", "description": "The search query to use. For example: 'Latest news on Nvidia stock performance'"},
#                 },
#                 "required": ["query"]
#             }
#         }
#     }]
# )
# assistant_id = assistant.id
# print(f"Assistant ID: {assistant_id}")


@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':  
        # conversation loop
        while True:
            print("\n")
            user_input = request.form.get('query', '')
            if not user_input:
                return render_template('index.html', response="Please enter a query.")

            if user_input.lower() == 'exit':
                end_conversation(assistant_id)
                break

            # Create a thread
            thread = client.beta.threads.create()
            print("\n")
            print(f"Thread: {thread}")

            # Create a message
            message = client.beta.threads.messages.create(
                thread_id=thread.id,
                role="user",
                content=user_input,
            )

            # Create a run
            run = client.beta.threads.runs.create(
                thread_id=thread.id,
                assistant_id=assistant_id,
            )
            print(f"Run ID: {run.id}")

            # Wait for run to complete
            run = wait_for_run_completion(thread.id, run.id)

            if run.status == 'failed':
                print(run.error)
                continue
            elif run.status == 'requires_action':
                run = submit_tool_outputs(thread.id, run.id, run.required_action.submit_tool_outputs.tool_calls)
                run = wait_for_run_completion(thread.id, run.id)

            # Print messages from the thread
            print("\n")
            reply = print_messages_from_thread(thread.id)
            
            # Clear the thread
            thread = client.beta.threads.delete(thread.id)
            print("Thread Deleted")
            
            return render_template('index.html', query=user_input, response_with_links=reply)
    
    else:
        return render_template('index.html')

# Custom route for handling external links
@app.route('/open_url', methods=['POST'])
def open_url():
    if request.method == 'POST':
        url = request.form['url']
        return redirect(url)

if __name__ == '__main__':
    app.run()
