#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Types/SlateEnums.h"
#include "Input/Reply.h"
#include "AgentEmbodimentGameMode.generated.h"

class UCameraComponent;
class SWidget;
class SEditableTextBox;
class STextBlock;

/** Optional integration example: a separate local human body and native chat panel. */
UCLASS(Blueprintable)
class AGENTEMBODIMENT_API AEmbodimentHumanCharacter : public ACharacter
{
    GENERATED_BODY()
public:
    AEmbodimentHumanCharacter();
    virtual void Tick(float DeltaSeconds) override;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Embodiment")
    TObjectPtr<UCameraComponent> HumanCamera;
};

UCLASS()
class AGENTEMBODIMENT_API AEmbodimentPlayerController : public APlayerController
{
    GENERATED_BODY()
public:
    virtual void Tick(float DeltaSeconds) override;
    bool IsChatOpen() const { return bChatOpen; }
protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
private:
    TSharedPtr<SWidget> ChatPanel;
    TSharedPtr<SEditableTextBox> ChatInput;
    TSharedPtr<STextBlock> ChatHistory;
    bool bChatOpen = false;
    bool bReady = false;
    FString LastTranscript;
    void OpenChat();
    void CloseChat();
    void SubmitChat(const FText& Text, ETextCommit::Type Type);
    FReply ChatKeyDown(const FGeometry& Geometry, const FKeyEvent& Event);
};

UCLASS(Blueprintable)
class AGENTEMBODIMENT_API AAgentEmbodimentGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AAgentEmbodimentGameMode();
};
