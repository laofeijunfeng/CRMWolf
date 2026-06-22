---
name: langchain
description: Build LLM applications with LangChain framework. Covers chains, agents, RAG pipelines, Anthropic/OpenAI integrations, LangGraph orchestration, and streaming.
---

# LangChain Development

Guidance for building LLM applications with LangChain framework. Use when the user asks about LangChain, building AI chains, agents, RAG pipelines, or working with LLM integrations.

## When to Use

- Building LLM-powered applications
- Creating chains, agents, or retrieval pipelines
- Integrating with OpenAI, Anthropic, or other LLM providers
- Implementing RAG (Retrieval Augmented Generation)
- Working with embeddings and vector stores
- Tool/function calling with LLMs

## Core Concepts

### LangChain Expression Language (LCEL)

The pipe operator `|` chains components:

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

chain = prompt | llm | output_parser
result = chain.invoke({"topic": "cats"})
```

### Key Abstractions

| Component | Purpose | Example |
|-----------|---------|---------|
| **PromptTemplate** | Format inputs for LLM | `ChatPromptTemplate.from_template("Tell me about {topic}")` |
| **LLM/ChatModel** | Generate responses | `ChatOpenAI(model="gpt-4")`, `ChatAnthropic(model="claude-3-opus")` |
| **OutputParser** | Parse LLM output | `StrOutputParser()`, `JsonOutputParser()` |
| **Runnable** | Base interface for all components | `.invoke()`, `.stream()`, `.batch()` |
| **VectorStore** | Store/search embeddings | `FAISS`, `Pinecone`, `Chroma` |
| **Retriever** | Retrieve relevant docs | `vectorstore.as_retriever()` |

### Runnable Interface Methods

| Method | Description |
|--------|-------------|
| `invoke()` | Single input, single output |
| `stream()` | Single input, stream output |
| `batch()` | Multiple inputs, multiple outputs |
| `ainvoke()` | Async version |
| `map()` | Parallel execution |

## Python SDK

### Installation

```bash
pip install langchain langchain-openai langchain-anthropic
```

### Anthropic Integration

```python
from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(
    model="claude-opus-4-8",
    temperature=0.7,
    max_tokens=4096
)

# Streaming
for chunk in llm.stream("Hello"):
    print(chunk.content, end="", flush=True)
```

### OpenAI Integration

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
```

### Prompt Templates

```python
from langchain_core.prompts import ChatPromptTemplate

# Simple template
prompt = ChatPromptTemplate.from_template("What is {topic}?")

# With system message
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant."),
    ("human", "{input}")
])
```

### Output Parsing

```python
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser

# String output
parser = StrOutputParser()

# JSON output with schema
from pydantic import BaseModel

class Answer(BaseModel):
    answer: str
    sources: list[str]

parser = JsonOutputParser(pydantic_object=Answer)

# Include format instructions in prompt
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant.\n{format_instructions}"),
    ("human", "{question}")
])
prompt.partial(format_instructions=parser.get_format_instructions())
```

### Chains

```python
# Simple chain
chain = prompt | llm | parser

# Invoke
result = chain.invoke({"question": "What is the capital of France?"})

# Stream
for chunk in chain.stream({"question": "Hello"}):
    print(chunk)

# Batch
results = chain.batch([
    {"question": "What is Python?"},
    {"question": "What is LangChain?"}
])
```

### RAG Pipeline

```python
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

# Load and split documents
loader = TextLoader("doc.txt")
docs = loader.load()
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
chunks = splitter.split_documents(docs)

# Create vector store
embeddings = OpenAIEmbeddings()
vectorstore = FAISS.from_documents(chunks, embeddings)

# Create retriever
retriever = vectorstore.as_retriever(search_kwargs={"k": 4})

# RAG chain
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

rag_chain = (
    {"context": retriever, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

result = rag_chain.invoke("What does the document say about X?")
```

### Tools and Agents

```python
from langchain_core.tools import tool

@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    # Implementation
    return "Results..."

@tool
def calculate(expression: str) -> float:
    """Calculate a mathematical expression."""
    return eval(expression)

# Bind tools to LLM
llm_with_tools = llm.bind_tools([search_web, calculate])

# Agent with LangGraph (recommended)
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(llm, [search_web, calculate])
result = agent.invoke({"messages": [("human", "What is the weather in Tokyo?")]})
```

## LangGraph (Agent Orchestration)

LangGraph is the modern way to build agents in LangChain.

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage

class State(TypedDict):
    messages: Annotated[list[BaseMessage], "The conversation history"]
    next: str

# Define nodes
def agent_node(state: State):
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

def tool_node(state: State):
    # Execute tools
    return {"messages": [tool_result]}

# Build graph
graph = StateGraph(State)
graph.add_node("agent", agent_node)
graph.add_node("tools", tool_node)
graph.add_edge("agent", "tools")
graph.add_edge("tools", END)

app = graph.compile()
```

## JavaScript SDK

### Installation

```bash
npm install @langchain/core @langchain/openai @langchain/anthropic
```

### Basic Usage

```typescript
import { ChatPromptTemplate } from "@langchain/core/prompts";
import { ChatOpenAI } from "@langchain/openai";
import { StringOutputParser } from "@langchain/core/output_parsers";

const prompt = ChatPromptTemplate.fromTemplate("What is {topic}?");
const llm = new ChatOpenAI({ model: "gpt-4o" });
const parser = new StringOutputParser();

const chain = prompt.pipe(llm).pipe(parser);

const result = await chain.invoke({ topic: "LangChain" });
```

### Streaming

```typescript
const stream = await chain.stream({ topic: "AI" });
for await (const chunk of stream) {
    console.log(chunk);
}
```

## Best Practices

### 1. Use LCEL for Composition

Prefer the pipe operator over legacy chain classes:

```python
# ✅ Modern LCEL
chain = prompt | llm | parser

# ❌ Legacy (deprecated)
chain = LLMChain(prompt=prompt, llm=llm)
```

### 2. Streaming for User Experience

Always stream to UI when possible:

```python
for chunk in chain.stream(inputs):
    yield chunk  # SSE or WebSocket
```

### 3. Error Handling

```python
from langchain_core.runnables import RunnableRetry

chain_with_retry = chain.with_retry(
    stop_after_attempt=3,
    wait_exponential_jitter=True
)
```

### 4. Caching for Cost

```python
from langchain_core.caches import InMemoryCache
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4o",
    cache=InMemoryCache()  # Cache identical prompts
)
```

### 5. Prompt Engineering

```python
# Use system prompts for role definition
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a {role}. Be concise and accurate."),
    ("human", "{input}"),
    ("placeholder", "{history}")  # For conversation history
])
```

### 6. Tracing with LangSmith

```python
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "your-api-key"

# All runs will be traced
chain.invoke(inputs)  # Logged to LangSmith
```

## Common Patterns

### Conversation with Memory

```python
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

chain_with_history = RunnableWithMessageHistory(
    chain,
    get_session_history=lambda session_id: ChatMessageHistory(),
    input_messages_key="input",
    history_messages_key="history"
)
```

### Parallel Execution

```python
from langchain_core.runnables import RunnableParallel

parallel_chain = RunnableParallel({
    "summary": summary_chain,
    "sentiment": sentiment_chain,
    "keywords": keyword_chain
})

results = parallel_chain.invoke({"text": long_text})
```

### Conditional Routing

```python
from langchain_core.runnables import RunnableBranch

branch = RunnableBranch(
    (lambda x: x["type"] == "question", question_chain),
    (lambda x: x["type"] == "command", command_chain),
    default_chain
)
```

## API Reference Quick Links

| Resource | URL |
|----------|-----|
| LangChain Docs | https://python.langchain.com/docs/ |
| LangGraph Docs | https://langchain-ai.github.io/langgraph/ |
| LangSmith | https://smith.langchain.com/ |
| JS Docs | https://js.langchain.com/docs/ |
| Hub (Prompts) | https://smith.langchain.com/hub |

## Key Warnings

- ❌ **Avoid legacy chains**: `LLMChain`, `SimpleSequentialChain` are deprecated
- ❌ **Avoid agent_classes**: Use LangGraph instead
- ✅ **Use LCEL**: Pipe operator `|` for composition
- ✅ **Use LangGraph**: For agents with state and control flow
- ✅ **Use Runnable interface**: `.invoke()`, `.stream()`, `.batch()`