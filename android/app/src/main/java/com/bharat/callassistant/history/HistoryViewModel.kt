package com.bharat.callassistant.history

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

@HiltViewModel
class HistoryViewModel @Inject constructor(
    repository: HistoryRepository,
) : ViewModel() {
    val entries: StateFlow<List<HistoryEntry>> = repository.entries()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())
}
