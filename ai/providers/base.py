"""
Base class for LLM providers.
"""
from abc import ABC, abstractmethod
from typing import Optional


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    def complete(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        timeout: float = 5.0
    ) -> str:
        """
        Send a completion request to the LLM.
        
        Args:
            system_prompt: The system/instruction prompt
            user_prompt: The user's query/context
            timeout: Maximum time to wait for response
            
        Returns:
            The LLM's response text
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging/debugging."""
        pass
    
    def is_available(self) -> bool:
        """Check if the provider is properly configured."""
        return True

