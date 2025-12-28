import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from typing import Dict, Any, List, Optional
from app.services.extractors.base import BaseExtractor
from app.services.embeddings import EmbeddingService
from app.services.llm import LLMService
from app.models.parameter_specs import PARAMETER_SPECS, ParameterCategory, ExtractionStatus
from app.services.extractors.crif_parser import parse_crif_report
from app.services.rag_service import RAGService
from config import (
    CONFIDENCE_METHOD_WEIGHTS,
    SIMILARITY_BOOST_THRESHOLDS,
    USE_EMBEDDING_GUIDED_EXTRACTION,
    ENABLE_DIRECT_PARSING_FALLBACK,
    ENABLE_RAG
)

logger = logging.getLogger(__name__)

class CRIFExtractor(BaseExtractor):
    def __init__(self, embedding_service: EmbeddingService, llm_service: LLMService):
        self.embedding_service = embedding_service
        self.llm_service = llm_service

        # Initialize RAG service if enabled
        self.rag_service = None
        if ENABLE_RAG:
            self.rag_service = RAGService()
            if self.rag_service.initialize():
                logger.info("RAG service initialized successfully")
            else:
                logger.warning("RAG service initialization failed, continuing without RAG")
                self.rag_service = None

    def extract(self, parsed_doc: Dict[str, Any], parameters: List[Dict]) -> Dict[str, Any]:
        extracted_results = {}

        # Parse CRIF report into structured model
        crif_report = parse_crif_report(parsed_doc)

        # Prepare document chunks for embedding-based retrieval
        # Check if pre-embedded chunks are available (optimization for repeated extractions)
        if '_embedded_chunks' in parsed_doc:
            document_chunks = parsed_doc['_embedded_chunks']
        else:
            document_chunks = self._prepare_document_chunks(parsed_doc)

        for param in parameters:
            param_id = param['id']
            param_name = param['name']

            logger.info(f"Extracting parameter: {param_name} ({param_id})")

            spec = PARAMETER_SPECS.get(param_id)
            if not spec:
                logger.warning(f"No spec found for {param_id}, skipping")
                extracted_results[param_id] = {
                    "value": None,
                    "source": "Parameter spec not found",
                    "confidence": 0.0,
                    "status": ExtractionStatus.EXTRACTION_FAILED
                }
                continue

            # Route to appropriate extraction method based on category
            if spec.category == ParameterCategory.POLICY:
                result = self._extract_policy(spec)
            elif USE_EMBEDDING_GUIDED_EXTRACTION:
                result = self._extract_with_embeddings(spec, crif_report, document_chunks)
            else:
                # Fallback to direct extraction (legacy mode)
                result = self._extract_direct_legacy(spec, crif_report, parsed_doc)

            extracted_results[param_id] = result

        return extracted_results

    def _prepare_document_chunks(self, parsed_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Prepare document chunks for embedding-based retrieval.
        Limits chunk size to stay within embedding model's token limit.
        """
        chunks = []
        max_chunk_chars = 1500  # Conservative limit for embedding model

        # Add tables as chunks (truncate if too large)
        for idx, table in enumerate(parsed_doc.get('tables', [])):
            content = str(table.get('dataframe', ''))
            if len(content) > max_chunk_chars:
                content = content[:max_chunk_chars]
                logger.debug(f"Truncated table {idx + 1} to {max_chunk_chars} chars")

            chunk = {
                'type': 'table',
                'index': idx,
                'content': content,
                'source': f"Table {idx + 1}",
                'data': table
            }
            chunks.append(chunk)

        # Add text chunks (truncate if too large)
        for idx, text_chunk in enumerate(parsed_doc.get('chunks', [])):
            content = text_chunk.get('text', '')
            if len(content) > max_chunk_chars:
                content = content[:max_chunk_chars]
                logger.debug(f"Truncated text chunk {idx + 1} to {max_chunk_chars} chars")

            chunk = {
                'type': 'text',
                'index': idx,
                'content': content,
                'source': f"Text Chunk {idx + 1}",
                'data': text_chunk
            }
            chunks.append(chunk)

        logger.info(f"Prepared {len(chunks)} document chunks for embedding retrieval")
        return chunks

    def _extract_with_embeddings(
        self,
        spec,
        crif_report,
        document_chunks: List[Dict[str, Any]]
    ) -> Dict:
        """
        Extract parameter using embedding-guided approach:
        1. Use embeddings to find relevant chunks
        2. (Optional) Retrieve domain knowledge via RAG
        3. Extract programmatically from those chunks
        """
        # Create query from parameter spec
        query = f"{spec.name}: {spec.description}"

        # Get domain knowledge context if RAG is enabled
        rag_context = ""
        if self.rag_service:
            rag_context = self.rag_service.get_context_for_parameter(
                spec.name,
                spec.description
            )
            if rag_context:
                logger.debug(f"Retrieved RAG context for {spec.id}: {len(rag_context)} chars")

        # Find relevant chunks using embeddings
        relevant_chunks = self.embedding_service.find_relevant_chunks(
            query=query,
            chunks=document_chunks
        )

        if not relevant_chunks:
            logger.warning(f"No relevant chunks found for {spec.id}")
            return {
                "value": None,
                "source": "No relevant sections found",
                "confidence": 0.0,
                "status": ExtractionStatus.NOT_FOUND,
                "rag_context": rag_context if rag_context else None
            }

        # Get the best matching chunk
        best_chunk = relevant_chunks[0]
        similarity_score = best_chunk.get('score', 0.0)

        logger.info(
            f"Found relevant chunk for {spec.id} with similarity={similarity_score:.3f}"
        )

        # Extract programmatically based on category
        # Use chunk-aware extraction: embeddings guide WHERE, deterministic extracts WHAT
        if spec.category == ParameterCategory.DIRECT:
            result = self._extract_direct_from_chunk(spec, crif_report, best_chunk)
        elif spec.category == ParameterCategory.FLAG:
            result = self._extract_flag_from_chunk(spec, crif_report, best_chunk)
        elif spec.category == ParameterCategory.DERIVED:
            result = self._extract_derived_from_chunk(spec, crif_report, best_chunk)
        else:
            result = {
                "value": None,
                "source": "Unknown category",
                "confidence": 0.0,
                "status": ExtractionStatus.EXTRACTION_FAILED
            }

        # If programmatic extraction failed and RAG is enabled, try LLM fallback
        if result.get('value') is None and self.rag_service and rag_context:
            logger.info(f"Programmatic extraction failed for {spec.id}, trying LLM with RAG context")

            llm_result = self._extract_with_llm_and_rag(
                spec=spec,
                chunk=best_chunk,
                rag_context=rag_context
            )

            if llm_result.get('value') is not None:
                result = llm_result
                # Boost confidence based on similarity score
                result['confidence'] *= self._get_similarity_boost(similarity_score)
                result['similarity_score'] = similarity_score
                logger.info(f"LLM extraction succeeded for {spec.id}: {result['value']}")
                return result
            else:
                logger.warning(f"LLM extraction also failed for {spec.id}")

        # Boost confidence based on similarity score (for programmatic extraction)
        if result.get('value') is not None:
            original_confidence = result.get('confidence', 0.0)
            similarity_boost = self._get_similarity_boost(similarity_score)
            result['confidence'] = original_confidence * similarity_boost
            result['similarity_score'] = similarity_score
            result['status'] = ExtractionStatus.EXTRACTED
            result['extraction_method'] = 'programmatic'

            # Add RAG context if available (for debugging/transparency)
            if rag_context:
                result['rag_context'] = rag_context

        return result

    def _extract_direct_from_report(self, spec, crif_report) -> Dict:
        """Extract DIRECT parameters from parsed CRIF report"""
        if spec.id == "bureau_credit_score":
            value = crif_report.bureau_score
            source = "Verification Table"
        elif spec.id == "bureau_written_off_debt_amount":
            value = crif_report.total_writeoff_amount
            source = "Account Summary Table"
        elif spec.id == "bureau_max_loans":
            value = int(crif_report.total_accounts_count)
            source = "Account Summary Table"
        elif spec.id == "bureau_max_active_loans":
            value = int(crif_report.active_accounts_count)
            source = "Account Summary Table"
        elif spec.id == "bureau_credit_inquiries":
            value = crif_report.credit_inquiries_count
            source = "Inquiry Table"
        else:
            value = None
            source = "Unknown direct parameter"

        confidence = self._calculate_confidence(spec, value, "embedding_guided")

        return {
            "value": value,
            "source": source,
            "confidence": confidence
        }

    def _extract_flag_from_report(self, spec, crif_report) -> Dict:
        """Extract FLAG parameters from parsed CRIF report"""
        if spec.id == "bureau_suit_filed":
            checker = lambda acc: acc.has_suit_filed()
            has_flag, matched = crif_report.has_flag_in_any_account(checker)
        elif spec.id == "bureau_wilful_default":
            checker = lambda acc: acc.has_wilful_default()
            has_flag, matched = crif_report.has_flag_in_any_account(checker)
        elif spec.id == "bureau_settlement_writeoff":
            checker = lambda acc: acc.has_settlement_writeoff()
            has_flag, matched = crif_report.has_flag_in_any_account(checker)
        elif spec.id == "bureau_ntc_accepted":
            has_flag, matched = False, 0
        else:
            has_flag, matched = False, 0

        value = has_flag
        total_accounts = len(crif_report.accounts)

        confidence = self._calculate_confidence(spec, value, "embedding_guided")

        return {
            "value": value,
            "source": f"Account Remarks ({matched}/{total_accounts} accounts)",
            "confidence": confidence
        }

    def _extract_derived_from_report(self, spec, crif_report) -> Dict:
        """Extract DERIVED parameters from parsed CRIF report"""
        if spec.id == "bureau_dpd_30":
            value = crif_report.count_dpd_accounts(30)
        elif spec.id == "bureau_dpd_60":
            value = crif_report.count_dpd_accounts(60)
        elif spec.id == "bureau_dpd_90":
            value = crif_report.count_dpd_accounts(90)
        elif spec.id == "bureau_no_live_pl_bl":
            value = not crif_report.has_live_pl_bl()
        else:
            value = None

        total_accounts = len(crif_report.accounts)

        confidence = self._calculate_confidence(spec, value, "embedding_guided")

        return {
            "value": value,
            "source": f"Computed from {total_accounts} accounts",
            "confidence": confidence
        }

    def _extract_policy(self, spec) -> Dict:
        """Extract POLICY parameters (not in document)"""
        return {
            "value": None,
            "source": "Not applicable (policy parameter)",
            "confidence": 0.0,
            "status": ExtractionStatus.NOT_APPLICABLE
        }

    def _extract_direct_from_chunk(self, spec, crif_report, best_chunk: Dict[str, Any]) -> Dict:
        """
        Extract DIRECT parameters using chunk-aware approach:
        1. Try to extract from best_chunk['data'] (the relevant table/chunk)
        2. Fall back to crif_report if chunk extraction fails
        """
        from app.services.extractors.crif_parser import (
            extract_bureau_score_from_df,
            extract_account_summary_from_df,
            extract_credit_inquiries_from_df
        )

        value = None
        source = "Unknown"
        chunk_used = False

        # Try chunk-based extraction first
        if best_chunk.get('type') == 'table' and best_chunk.get('data'):
            chunk_table = best_chunk['data']
            df = chunk_table.get('dataframe')

            if spec.id == "bureau_credit_score":
                value = extract_bureau_score_from_df(df)
                if value is not None:
                    source = f"Verification Table (from {best_chunk.get('source', 'chunk')})"
                    chunk_used = True
            elif spec.id == "bureau_written_off_debt_amount":
                summary = extract_account_summary_from_df(df)
                if summary:
                    value = summary.get('total_writeoff_amount')
                    source = f"Account Summary Table (from {best_chunk.get('source', 'chunk')})"
                    chunk_used = True
            elif spec.id == "bureau_max_loans":
                summary = extract_account_summary_from_df(df)
                if summary:
                    value = int(summary.get('total_accounts', 0))
                    source = f"Account Summary Table (from {best_chunk.get('source', 'chunk')})"
                    chunk_used = True
            elif spec.id == "bureau_max_active_loans":
                summary = extract_account_summary_from_df(df)
                if summary:
                    value = int(summary.get('active_accounts', 0))
                    source = f"Account Summary Table (from {best_chunk.get('source', 'chunk')})"
                    chunk_used = True
            elif spec.id == "bureau_credit_inquiries":
                value = extract_credit_inquiries_from_df(df)
                if value is not None:
                    source = f"Inquiry Table (from {best_chunk.get('source', 'chunk')})"
                    chunk_used = True

        # Fall back to full report if chunk extraction failed
        if value is None:
            logger.debug(f"Chunk extraction failed for {spec.id}, falling back to full report")
            return self._extract_direct_from_report(spec, crif_report)

        confidence = self._calculate_confidence(spec, value, "chunk_aware")

        if chunk_used:
            logger.debug(f"✓ Chunk-aware extraction used for {spec.id} from {best_chunk.get('source')}")

        return {
            "value": value,
            "source": source,
            "confidence": confidence
        }

    def _extract_flag_from_chunk(self, spec, crif_report, best_chunk: Dict[str, Any]) -> Dict:
        """
        Extract FLAG parameters using chunk-aware approach:
        1. Try to extract from best_chunk (if it's account remarks text)
        2. Fall back to full report if chunk extraction fails
        """
        value = False
        matched = 0
        total_accounts = len(crif_report.accounts)

        # Try chunk-based extraction if it's a text chunk with account information
        if best_chunk.get('type') == 'text' and best_chunk.get('data'):
            chunk_text = best_chunk['data'].get('text', '')

            # Parse accounts from this chunk only
            from app.services.extractors.crif_parser import parse_account_from_text

            # Split chunk into account blocks and parse them
            account_blocks = chunk_text.split('Account Number:')[1:]  # Skip header
            chunk_accounts = []

            for block in account_blocks:
                account = parse_account_from_text('Account Number:' + block)
                if account:
                    chunk_accounts.append(account)

            # Check flags in chunk accounts only
            if chunk_accounts:
                if spec.id == "bureau_suit_filed":
                    matched = sum(1 for acc in chunk_accounts if acc.has_suit_filed())
                    value = matched > 0
                elif spec.id == "bureau_wilful_default":
                    matched = sum(1 for acc in chunk_accounts if acc.has_wilful_default())
                    value = matched > 0
                elif spec.id == "bureau_settlement_writeoff":
                    matched = sum(1 for acc in chunk_accounts if acc.has_settlement_writeoff())
                    value = matched > 0

                if matched > 0:
                    source = f"Account Remarks ({matched}/{len(chunk_accounts)} accounts in chunk)"
                    confidence = self._calculate_confidence(spec, value, "chunk_aware")
                    return {
                        "value": value,
                        "source": source,
                        "confidence": confidence
                    }

        # Fall back to full report
        logger.debug(f"Chunk extraction failed for {spec.id}, falling back to full report")
        return self._extract_flag_from_report(spec, crif_report)

    def _extract_derived_from_chunk(self, spec, crif_report, best_chunk: Dict[str, Any]) -> Dict:
        """
        Extract DERIVED parameters using chunk-aware approach:
        For DPD counts, we still compute across all accounts (embedding only influences confidence).
        For "no live PL/BL", we validate but don't restrict.
        """
        # Derived fields are inherently global, so we use full report
        # but the embedding helps with confidence scoring
        return self._extract_derived_from_report(spec, crif_report)

    def _extract_with_llm_and_rag(
        self,
        spec,
        chunk: Dict[str, Any],
        rag_context: str
    ) -> Dict:
        """
        Extract parameter using LLM with RAG context.
        Used as fallback when programmatic extraction fails.

        This is useful when:
        - PDF structure changes (different headings/column names)
        - New parameter types not in spec
        - Ambiguous or unstructured data
        """
        # Build prompt with RAG context
        prompt = f"""You are extracting structured data from a credit bureau report.

Domain Knowledge:
{rag_context}

Document Section:
{chunk['content'][:2000]}

Extract the following parameter:
- Name: {spec.name}
- Description: {spec.description}
- Expected Type: {getattr(spec, 'expected_type', 'string')}

Instructions:
1. Use the domain knowledge above to understand what to look for
2. Extract the EXACT value from the document section
3. If the value is not found in this section, return exactly: NOT_FOUND
4. If the parameter is not applicable to this document, return exactly: NOT_APPLICABLE
5. Return ONLY the extracted value, nothing else (no explanations, no formatting)

Value:"""

        try:
            # Call LLM
            response = self.llm_service.generate(prompt)
            value = response.strip()

            logger.debug(f"LLM response for {spec.id}: {value}")

            # Parse response
            if value == "NOT_FOUND" or not value:
                return {
                    "value": None,
                    "source": chunk['source'],
                    "confidence": 0.0,
                    "status": ExtractionStatus.NOT_FOUND,
                    "extraction_method": "llm_with_rag",
                    "rag_context": rag_context
                }
            elif value == "NOT_APPLICABLE":
                return {
                    "value": None,
                    "source": chunk['source'],
                    "confidence": 0.0,
                    "status": ExtractionStatus.NOT_APPLICABLE,
                    "extraction_method": "llm_with_rag",
                    "rag_context": rag_context
                }
            else:
                # Try to convert to expected type
                expected_type = getattr(spec, 'expected_type', 'string')
                try:
                    if expected_type == "int":
                        # Remove common formatting
                        value = value.replace(',', '').replace(' ', '')
                        value = int(float(value))  # Handle "123.0" -> 123
                    elif expected_type == "float":
                        value = value.replace(',', '').replace(' ', '')
                        value = float(value)
                    elif expected_type == "bool":
                        value = value.lower() in ["true", "yes", "1", "y"]
                    # else: keep as string
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Could not convert LLM output to {expected_type}: {e}")
                    # Keep as string

                return {
                    "value": value,
                    "source": chunk['source'],
                    "confidence": 0.6,  # Lower confidence for LLM extraction
                    "status": ExtractionStatus.EXTRACTED,
                    "extraction_method": "llm_with_rag",
                    "rag_context": rag_context
                }

        except Exception as e:
            logger.error(f"LLM extraction failed for {spec.id}: {e}")
            return {
                "value": None,
                "source": chunk['source'],
                "confidence": 0.0,
                "status": ExtractionStatus.EXTRACTION_FAILED,
                "extraction_method": "llm_with_rag",
                "error": str(e)
            }

    def _calculate_confidence(self, spec, value, method) -> float:
        """Calculate confidence score for extraction"""
        method_confidence = CONFIDENCE_METHOD_WEIGHTS.get(method, 0.5)

        if not spec.validate(value):
            return 0.0

        if value is None:
            type_certainty = 0.0
        elif isinstance(value, spec.expected_type):
            type_certainty = 1.0
        else:
            type_certainty = 0.5

        return method_confidence * type_certainty

    def _get_similarity_boost(self, similarity_score: float) -> float:
        """Get confidence boost multiplier based on similarity score"""
        for level, (threshold, boost) in SIMILARITY_BOOST_THRESHOLDS.items():
            if similarity_score >= threshold:
                return boost
        return 0.5  # Very low similarity
