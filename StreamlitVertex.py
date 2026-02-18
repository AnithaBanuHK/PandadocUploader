import streamlit as st
import vertexai
import os
from langchain_google_vertexai import ChatVertexAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Initialize Vertex AI
vertexai.init(
    project="aac-dw-dev",
    location="europe-west1"
)

# Prompt template
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a helpful assistant. Please respond to user queries clearly."),
        ("user", "Question: {question}")
    ]
)

# Streamlit UI
st.title("LangChain + Gemini Demo")
input_text = st.text_input("Search the topic you want")


# Load a Gemini model available in Vertex AI
llm = ChatVertexAI(model=os.getenv("VERTEX_MODEL_NAME", "gemini-2.0-flash-lite"), temperature=0.1)


output_parser = StrOutputParser()

chain = prompt | llm | output_parser

if input_text:
    response = chain.invoke({"question": input_text})
    st.write(response)
