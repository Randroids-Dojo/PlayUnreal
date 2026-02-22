// PlayUnrealAutomationModule.cpp

#include "PlayUnrealAutomationModule.h"
#include "Modules/ModuleManager.h"

#define LOCTEXT_NAMESPACE "FPlayUnrealAutomationModule"

void FPlayUnrealAutomationModule::StartupModule()
{
	UE_LOG(LogTemp, Log, TEXT("PlayUnrealAutomation: Module started"));
}

void FPlayUnrealAutomationModule::ShutdownModule()
{
	UE_LOG(LogTemp, Log, TEXT("PlayUnrealAutomation: Module shutdown"));
}

#undef LOCTEXT_NAMESPACE

IMPLEMENT_MODULE(FPlayUnrealAutomationModule, PlayUnrealAutomation)
