# LLM Knowledge for Odoo

Comprehensive knowledge base and RAG (Retrieval Augmented Generation) system with consolidated resource management, document processing, vector storage, and intelligent retrieval capabilities.

## Overview

The LLM Knowledge module provides a complete solution for building knowledge-driven AI applications in Odoo. **Version 18.0.1.1.0** consolidates functionality from the former `llm_resource` module, combining document resource management with advanced RAG capabilities in a single, cohesive system.

### Core Capabilities

- **Consolidated Resource Management** - Document processing, parsing, and storage (formerly `llm_resource`)
- **RAG System** - Retrieval-Augmented Generation with vector search
- **Document Processing Pipeline** - Retrieve → Parse → Chunk → Embed → Index
- **Vector Integration** - Seamless integration with multiple vector stores
- **Knowledge Collections** - Organized document grouping and management
- **Automated Processing** - Background processing and automation rules

## Key Features

### Consolidated Architecture (Version 18.0.1.1.0)

**Major Consolidation Benefits:**

- ✅ **Single Module**: Combined resource management and RAG functionality
- ✅ **Simplified Installation**: One module instead of two interdependent modules
- ✅ **Better Performance**: Reduced module loading overhead
- ✅ **Easier Maintenance**: Single codebase for all resource-related functionality
- ✅ **Enhanced Cohesion**: Resource management and RAG naturally coupled

**Migration**: Automatic migration from `llm_resource` preserves all existing data and functionality.

### Complete Processing Pipeline

**State Management:**

```
draft → retrieved → parsed → chunked → ready
```

1. **Retrieve**: Get content from sources (HTTP, attachments, etc.)
2. **Parse**: Convert content to markdown format
3. **Chunk**: Split content into manageable segments
4. **Embed**: Generate vector embeddings for chunks
5. **Index**: Store embeddings in vector database for search

### Resource Management

#### Document Resource Model

```python
class LLMResource(models.Model):
    _name = "llm.resource"
    _description = "LLM Resource"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(required=True)
    url = fields.Char()
    resource_type = fields.Selection([
        ('url', 'URL'),
        ('attachment', 'Attachment'),
        ('text', 'Text Content')
    ], required=True)

    # Processing states
    state = fields.Selection([
        ('draft', 'Draft'),
        ('retrieved', 'Retrieved'),
        ('parsed', 'Parsed'),
        ('chunked', 'Chunked'),
        ('ready', 'Ready')
    ], default='draft')

    # Content fields
    content = fields.Text()  # Raw retrieved content
    markdown_content = fields.Text()  # Parsed markdown

    # Processing metadata
    retrieval_date = fields.Datetime()
    parsing_date = fields.Datetime()
    chunking_date = fields.Datetime()
    embedding_date = fields.Datetime()

    def process_resource(self):
        """Complete processing pipeline"""
        self.retrieve()
        self.parse()
        self.chunk()
        self.embed()
        return True
```

#### Resource Retrieval System

**HTTP Retriever:**

```python
class LLMResourceHTTP(models.Model):
    _name = "llm.resource.http"
    _inherit = "llm.resource"

    def retrieve_content(self):
        """Retrieve content from HTTP URL"""
        import requests
        from bs4 import BeautifulSoup

        try:
            response = requests.get(self.url, timeout=30)
            response.raise_for_status()

            if 'text/html' in response.headers.get('content-type', ''):
                # Parse HTML content
                soup = BeautifulSoup(response.content, 'html.parser')

                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()

                self.content = soup.get_text()
            else:
                # Plain text content
                self.content = response.text

            self.retrieval_date = fields.Datetime.now()
            self.state = 'retrieved'

        except Exception as e:
            raise UserError(f"Failed to retrieve content: {str(e)}")
```

**Attachment Retriever:**

```python
def retrieve_from_attachment(self, attachment_id):
    """Retrieve content from Odoo attachment"""
    attachment = self.env['ir.attachment'].browse(attachment_id)

    if attachment.mimetype == 'application/pdf':
        self.content = self._extract_pdf_content(attachment.raw)
    elif attachment.mimetype in ['text/plain', 'text/html']:
        self.content = base64.b64decode(attachment.datas).decode('utf-8')
    elif attachment.mimetype in ['application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        self.content = self._extract_word_content(attachment.raw)
    else:
        raise UserError(f"Unsupported file type: {attachment.mimetype}")

    self.retrieval_date = fields.Datetime.now()
    self.state = 'retrieved'
```

#### Content Parsing System

**Multi-Format Parser:**

```python
class LLMResourceParser(models.Model):
    _name = "llm.resource.parser"

    def parse_to_markdown(self, content, content_type='html'):
        """Parse content to markdown format"""

        if content_type == 'html':
            return self._parse_html_to_markdown(content)
        elif content_type == 'pdf':
            return self._parse_pdf_to_markdown(content)
        elif content_type == 'docx':
            return self._parse_docx_to_markdown(content)
        elif content_type == 'plain':
            return self._parse_plain_to_markdown(content)
        else:
            return content  # Return as-is for unknown types

    def _parse_html_to_markdown(self, html_content):
        """Convert HTML to markdown"""
        import html2text

        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.body_width = 0  # Don't wrap lines

        markdown = h.handle(html_content)
        return self._clean_markdown(markdown)

    def _clean_markdown(self, markdown):
        """Clean up markdown formatting"""
        import re

        # Remove excessive blank lines
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)

        # Clean up list formatting
        markdown = re.sub(r'^\s*\*\s*$', '', markdown, flags=re.MULTILINE)

        # Remove leading/trailing whitespace
        markdown = markdown.strip()

        return markdown
```

### Knowledge Collections

#### Collection Management

```python
class LLMKnowledgeCollection(models.Model):
    _name = "llm.knowledge.collection"
    _description = "Knowledge Collection"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True)
    description = fields.Text()

    # Vector store integration
    store_id = fields.Many2one('llm.store', required=True)
    store_collection_id = fields.Many2one('llm.store.collection')

    # Resources and chunks
    resource_ids = fields.Many2many('llm.resource')
    chunk_ids = fields.One2many('llm.knowledge.chunk', 'collection_id')

    # Processing configuration
    chunk_size = fields.Integer(default=1000)
    chunk_overlap = fields.Integer(default=200)
    embedding_model_id = fields.Many2one('llm.model')

    def create_vector_collection(self):
        """Create corresponding vector store collection"""
        if not self.store_collection_id:
            collection = self.env['llm.store.collection'].create({
                'name': f"knowledge_{self.id}",
                'store_id': self.store_id.id,
                'dimension': self._get_embedding_dimension(),
                'distance_metric': 'cosine'
            })

            collection.create_collection()
            self.store_collection_id = collection.id

        return self.store_collection_id

    def process_all_resources(self):
        """Process all resources in collection"""
        for resource in self.resource_ids:
            if resource.state != 'ready':
                resource.process_resource()

        # Generate embeddings for all chunks
        self._generate_embeddings_for_chunks()

        return True
```

#### Document Chunking

```python
class LLMKnowledgeChunk(models.Model):
    _name = "llm.knowledge.chunk"
    _description = "Knowledge Chunk"

    content = fields.Text(required=True)
    chunk_index = fields.Integer(required=True)

    # Relationships
    resource_id = fields.Many2one('llm.resource', required=True)
    collection_id = fields.Many2one('llm.knowledge.collection', required=True)

    # Vector storage
    vector_id = fields.Char()  # ID in vector store
    embedding_model_id = fields.Many2one('llm.model')
    embedding_date = fields.Datetime()

    # Metadata
    token_count = fields.Integer()
    language = fields.Char()
    quality_score = fields.Float()

    def generate_embedding(self):
        """Generate and store embedding for this chunk"""
        if not self.embedding_model_id:
            self.embedding_model_id = self.collection_id.embedding_model_id

        if not self.embedding_model_id:
            raise UserError("No embedding model configured")

        # Generate embedding
        embedding = self.embedding_model_id.provider_id.embedding(
            text=self.content,
            model=self.embedding_model_id.name
        )

        # Store in vector database
        vector_id = f"chunk_{self.id}"
        metadata = {
            'chunk_id': self.id,
            'resource_id': self.resource_id.id,
            'collection_id': self.collection_id.id,
            'chunk_index': self.chunk_index,
            'token_count': self.token_count,
            'language': self.language or 'en',
            'resource_type': self.resource_id.resource_type,
            'source_url': self.resource_id.url
        }

        self.collection_id.store_collection_id.insert_vectors(
            vectors=[embedding],
            metadata=[metadata],
            ids=[vector_id]
        )

        self.vector_id = vector_id
        self.embedding_date = fields.Datetime.now()

        return True
```

### Advanced Text Chunking Strategies

#### Intelligent Chunking

```python
class ChunkingStrategy(models.Model):
    _name = "llm.chunking.strategy"

    def chunk_by_paragraphs(self, text, max_chunk_size=1000, overlap=200):
        """Chunk text by paragraphs with size limits"""
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            if len(current_chunk) + len(paragraph) <= max_chunk_size:
                current_chunk += paragraph + '\n\n'
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = paragraph + '\n\n'

        if current_chunk:
            chunks.append(current_chunk.strip())

        # Add overlap between chunks
        if overlap > 0:
            chunks = self._add_chunk_overlap(chunks, overlap)

        return chunks

    def chunk_by_sentences(self, text, max_chunk_size=1000):
        """Chunk text by sentences for better coherence"""
        import nltk

        sentences = nltk.sent_tokenize(text)
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) <= max_chunk_size:
                current_chunk += sentence + " "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + " "

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def chunk_by_semantic_similarity(self, text, model_id, similarity_threshold=0.7):
        """Advanced chunking based on semantic similarity"""
        sentences = self._split_into_sentences(text)
        embeddings = self._generate_sentence_embeddings(sentences, model_id)

        chunks = []
        current_chunk = [sentences[0]]

        for i in range(1, len(sentences)):
            similarity = self._cosine_similarity(
                embeddings[i-1],
                embeddings[i]
            )

            if similarity >= similarity_threshold:
                current_chunk.append(sentences[i])
            else:
                chunks.append(' '.join(current_chunk))
                current_chunk = [sentences[i]]

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks
```

### Vector Search and Retrieval

#### Semantic Search

```python
class KnowledgeRetriever(models.Model):
    _name = "llm.knowledge.retriever"

    def search_knowledge(self, query, collection_ids=None, limit=10, min_score=0.7):
        """Search knowledge base with query"""

        # Get collections to search
        if collection_ids:
            collections = self.env['llm.knowledge.collection'].browse(collection_ids)
        else:
            collections = self.env['llm.knowledge.collection'].search([])

        all_results = []

        for collection in collections:
            if not collection.store_collection_id:
                continue

            # Generate query embedding
            embedding_model = collection.embedding_model_id
            if not embedding_model:
                continue

            query_embedding = embedding_model.provider_id.embedding(
                text=query,
                model=embedding_model.name
            )

            # Search in vector store
            results = collection.store_collection_id.search_vectors(
                query_vector=query_embedding,
                limit=limit,
                filter_metadata={'collection_id': collection.id}
            )

            # Filter by minimum score
            filtered_results = [
                r for r in results
                if r.get('score', 0) >= min_score
            ]

            all_results.extend(filtered_results)

        # Sort by score and limit
        all_results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return all_results[:limit]

    def get_relevant_context(self, query, max_tokens=4000):
        """Get relevant context for RAG generation"""
        results = self.search_knowledge(query, limit=20)

        context_chunks = []
        total_tokens = 0

        for result in results:
            chunk_id = result['metadata']['chunk_id']
            chunk = self.env['llm.knowledge.chunk'].browse(chunk_id)

            chunk_tokens = chunk.token_count or len(chunk.content.split())

            if total_tokens + chunk_tokens <= max_tokens:
                context_chunks.append({
                    'content': chunk.content,
                    'source': chunk.resource_id.name,
                    'score': result.get('score', 0),
                    'url': chunk.resource_id.url
                })
                total_tokens += chunk_tokens
            else:
                break

        return context_chunks
```

### RAG Integration Examples

#### Knowledge-Enhanced Chat

```python
class RAGChatAssistant(models.Model):
    _name = "llm.assistant.rag"
    _inherit = "llm.assistant"

    knowledge_collection_ids = fields.Many2many('llm.knowledge.collection')
    use_rag = fields.Boolean(default=True)
    max_context_tokens = fields.Integer(default=4000)

    def generate_rag_response(self, user_query, thread_id):
        """Generate response with RAG context"""

        if not self.use_rag or not self.knowledge_collection_ids:
            return super().generate_response(user_query, thread_id)

        # Get relevant knowledge
        retriever = self.env['llm.knowledge.retriever']
        context = retriever.get_relevant_context(
            query=user_query,
            max_tokens=self.max_context_tokens
        )

        if not context:
            return super().generate_response(user_query, thread_id)

        # Build enhanced prompt
        context_text = self._format_context_for_prompt(context)
        enhanced_prompt = f\"\"\"
        Context from knowledge base:
        {context_text}

        User question: {user_query}

        Please answer the question using the provided context. If the context doesn't contain relevant information, say so clearly.
        \"\"\"

        # Generate response
        thread = self.env['llm.thread'].browse(thread_id)
        response = thread.generate_response(enhanced_prompt)

        # Add context sources to response metadata
        self._add_context_sources(response, context)

        return response

    def _format_context_for_prompt(self, context_chunks):
        """Format context chunks for inclusion in prompt"""
        formatted_chunks = []

        for i, chunk in enumerate(context_chunks, 1):
            formatted_chunks.append(f\"\"\"
            Source {i}: {chunk['source']}
            Relevance Score: {chunk['score']:.2f}
            Content: {chunk['content']}
            \"\"\"

        return '\n---\n'.join(formatted_chunks)
```

#### Automated Knowledge Updates

```python
class KnowledgeAutomation(models.Model):
    _name = "llm.knowledge.automation"

    def auto_update_web_resources(self):
        """Automatically update web-based resources"""
        web_resources = self.env['llm.resource'].search([
            ('resource_type', '=', 'url'),
            ('state', '=', 'ready')
        ])

        for resource in web_resources:
            try:
                # Check if content has changed
                old_content = resource.content
                resource.retrieve()

                if resource.content != old_content:
                    # Content changed, reprocess
                    resource.parse()
                    resource.chunk()
                    resource.embed()

                    self._notify_content_update(resource)

            except Exception as e:
                _logger.warning(f"Failed to update resource {resource.id}: {e}")

    def cleanup_outdated_chunks(self, days_old=30):
        """Remove chunks from outdated resources"""
        cutoff_date = fields.Datetime.now() - timedelta(days=days_old)

        outdated_resources = self.env['llm.resource'].search([
            ('retrieval_date', '<', cutoff_date),
            ('state', '=', 'ready')
        ])

        for resource in outdated_resources:
            # Remove from vector store
            chunks = resource.chunk_ids
            vector_ids = chunks.mapped('vector_id')

            for collection in resource.collection_ids:
                if collection.store_collection_id and vector_ids:
                    collection.store_collection_id.delete_vectors(ids=vector_ids)

            # Reset resource state
            resource.state = 'parsed'
            chunks.unlink()
```

## API Reference

### Core Resource Methods

```python
# Resource processing pipeline
def process_resource(self):
    """Complete processing: retrieve → parse → chunk → embed"""

def retrieve(self):
    """Retrieve content from source"""

def parse(self):
    """Parse content to markdown"""

def chunk(self):
    """Split content into chunks"""

def embed(self):
    """Generate embeddings and store in vector DB"""

# Resource management
def lock_resource(self):
    """Lock resource during processing"""

def unlock_resource(self):
    """Unlock resource after processing"""

def reset_to_state(self, state):
    """Reset resource to specific processing state"""
```

### Collection Methods

```python
# Collection management
def create_vector_collection(self):
    """Create vector store collection"""

def process_all_resources(self):
    """Process all resources in collection"""

def add_resources(self, resource_ids):
    """Add resources to collection"""

def remove_resources(self, resource_ids):
    """Remove resources from collection"""

# Search and retrieval
def search_content(self, query, limit=10):
    """Search collection content"""

def get_statistics(self):
    """Get collection statistics"""
```

## Configuration Examples

### Setting Up Knowledge Collection

```python
# Create knowledge collection
collection = env['llm.knowledge.collection'].create({
    'name': 'Product Documentation',
    'description': 'Technical documentation for all products',
    'store_id': pgvector_store.id,
    'chunk_size': 1000,
    'chunk_overlap': 200,
    'embedding_model_id': openai_embedding_model.id
})

collection.create_vector_collection()

# Add resources
resources = env['llm.resource'].create([
    {
        'name': 'Product Manual v1.0',
        'url': 'https://docs.company.com/product-manual',
        'resource_type': 'url'
    },
    {
        'name': 'FAQ Document',
        'resource_type': 'attachment',
        'attachment_id': faq_attachment.id
    }
])

collection.resource_ids = [(6, 0, resources.ids)]
collection.process_all_resources()
```

### Setting Up RAG Assistant

```python
# Create RAG-enabled assistant
rag_assistant = env['llm.assistant'].create({
    'name': 'Product Support Assistant',
    'role': 'Technical Support Specialist',
    'goal': 'Provide accurate product support using documentation',
    'knowledge_collection_ids': [(6, 0, [collection.id])],
    'use_rag': True,
    'max_context_tokens': 4000,
    'provider_id': openai_provider.id,
    'model_id': gpt4_model.id
})
```

## Migration Notes

### From llm_resource Module

**Automatic Migration (Version 18.0.1.1.0):**

- All `llm_resource` data automatically migrated to `llm_knowledge`
- Resource processing states preserved
- Collection relationships maintained
- Vector store connections updated
- No manual intervention required

**Enhanced Features Added:**

- Better resource management integration
- Improved processing pipeline
- Enhanced error handling and logging
- Optimized vector operations

### Breaking Changes

None - this is a consolidation update with full backward compatibility.

## Technical Specifications

### Module Information

- **Name**: LLM Knowledge
- **Version**: 18.0.1.1.0
- **Category**: Knowledge Management
- **License**: LGPL-3
- **Dependencies**: `llm`, `llm_store`, `mail`
- **Author**: Apexive Solutions LLC

### Key Models

- **`llm.resource`**: Document resource management (consolidated from `llm_resource`)
- **`llm.knowledge.collection`**: Knowledge collection organization
- **`llm.knowledge.chunk`**: Text chunks with embeddings
- **`llm.knowledge.retriever`**: Search and retrieval operations
- **`llm.resource.parser`**: Content parsing and conversion
- **`llm.resource.http`**: HTTP resource retrieval

### Processing States

| State       | Description                      | Operations Available |
| ----------- | -------------------------------- | -------------------- |
| `draft`     | Initial state                    | retrieve()           |
| `retrieved` | Content retrieved                | parse()              |
| `parsed`    | Content parsed to markdown       | chunk()              |
| `chunked`   | Content split into chunks        | embed()              |
| `ready`     | Embeddings generated and indexed | search, retrieve     |

## Performance Features

- **Batch Processing**: Efficient handling of large document sets
- **Incremental Updates**: Only reprocess changed content
- **Vector Optimization**: Automatic index optimization
- **Memory Management**: Efficient chunk processing
- **Parallel Processing**: Concurrent resource processing

## Security Features

- **Access Control**: Role-based access to collections and resources
- **Content Validation**: Sanitization of retrieved content
- **Rate Limiting**: Throttling of external resource retrieval
- **Audit Trail**: Complete tracking of resource processing

## Related Modules

- **`llm`**: Base infrastructure and provider framework
- **`llm_store`**: Vector storage abstraction layer
- **`llm_assistant`**: AI assistants with RAG integration
- **`llm_tool_knowledge`**: Knowledge search tool
- **`llm_knowledge_automation`**: Automation rules for knowledge processing

## Support & Resources

- **Documentation**: [GitHub Repository](https://github.com/apexive/odoo-llm)
- **Architecture Guide**: [OVERVIEW.md](../OVERVIEW.md)
- **Knowledge Examples**: [Knowledge Management Guide](examples/)
- **Community**: [GitHub Discussions](https://github.com/apexive/odoo-llm/discussions)

## License

This module is licensed under [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.html).

---

_© 2025 Apexive Solutions LLC. All rights reserved._
