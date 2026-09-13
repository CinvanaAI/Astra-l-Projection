#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "HAL/CriticalSection.h"
#include "AgentEmbodimentCharacter.generated.h"

class UCameraComponent;
class UStaticMeshComponent;
class USceneCaptureComponent2D;
class UTextureRenderTarget2D;
class FJsonObject;

/** Place one in your map. The agent owns this body; the local player owns another. */
UCLASS(Blueprintable)
class AGENTEMBODIMENT_API AAgentEmbodimentCharacter : public ACharacter
{
    GENERATED_BODY()
public:
    AAgentEmbodimentCharacter();
    virtual void Tick(float DeltaSeconds) override;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Embodiment")
    TObjectPtr<UCameraComponent> EyeCamera;

    /** Empty uses this project's Saved/AgentEmbodiment. -AgentQueue= overrides this. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Embodiment")
    FString QueueDirectory;

    /** Diagnostic engine cylinder appears only when the inherited Mesh has no asset. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Embodiment")
    bool bShowDiagnosticProxy = true;

    UFUNCTION(BlueprintCallable, Category="Embodiment")
    void LocalEmergencyStop();

    UFUNCTION(BlueprintCallable, Category="Embodiment")
    bool ReceiveHumanMessage(const FString& Text, FString& Error);

    UFUNCTION(BlueprintPure, Category="Embodiment")
    FString GetChatTranscript() const { return FString::Join(Transcript, TEXT("\n\n")); }

    bool IsQueueRunning() const { return bRunning; }
    static AAgentEmbodimentCharacter* FindAgent(UWorld* World);

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

    UPROPERTY(VisibleAnywhere, Category="Embodiment")
    TObjectPtr<UStaticMeshComponent> DiagnosticProxy;

    UPROPERTY(VisibleAnywhere, Category="Embodiment")
    TObjectPtr<USceneCaptureComponent2D> EyeCapture;

    UPROPERTY(Transient)
    TObjectPtr<UTextureRenderTarget2D> CaptureTarget;

private:
    struct FCommand
    {
        FString Id;
        FString Action = TEXT("invalid");
        FString Text;
        float Forward = 0;
        float Right = 0;
        float Seconds = .25f;
        float Speed = 150;
        float YawDelta = 0;
        float PitchDelta = 0;
        int64 ReplyToEventId = 0;
        bool bCapture = false;
    };

    FString QueueRoot;
    TUniquePtr<FSystemWideCriticalSection> QueueLock;
    FString SessionId;
    FString StartedAtUtc;
    bool bRunning = false;
    bool bMoving = false;
    double PollAt = 0;
    double HeartbeatAt = 0;
    double MoveDeadline = 0;
    double LastProgressAt = 0;
    FVector ProgressPosition = FVector::ZeroVector;
    FVector MoveDirection = FVector::ZeroVector;
    FRotator ViewRotation = FRotator::ZeroRotator;
    FCommand ActiveMove;
    int64 StopRevision = 0;
    int64 ChatEventId = 0;
    int64 ObservationId = 0;
    TArray<FString> Transcript;
    TSet<int64> HumanEventIds;
    TSharedPtr<FJsonObject> LatestHumanMessage;

    void PollQueue();
    bool ParseCommand(const TSharedPtr<FJsonObject>& Json, const FString& Id, FCommand& Command, FString& Error) const;
    void ExecuteCommand(const FCommand& Command);
    void FinishMove(const FString& Status, const FString& Error = FString());
    void StopMotor();
    void ApplyViewRotation();
    bool RecordSpeech(const FString& Speaker, const FString& Text, FString& Error, int64 ReplyToEventId = 0);
    TSharedRef<FJsonObject> MakeState();
    bool CaptureEye(const FString& Id, FString& ImagePath, FString& Error);
    void WriteReply(const FCommand& Command, const FString& Status, const FString& Error = FString());
    void WriteRuntime();
    bool AtomicJson(const FString& Filename, const TSharedRef<FJsonObject>& Json, bool bReplace = true) const;
};
