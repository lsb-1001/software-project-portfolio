package com.travel.travel.entity;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import java.time.LocalDateTime;

@Entity
public class Reservation {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  private String username;

  private Long travelId;

  private Long scheduleId;

  private int people;

  private LocalDateTime reserveDate;

  public Reservation() {
    this.reserveDate = LocalDateTime.now();
  }

  public Long getId() {
    return id;
  }

  public String getUsername() {
    return username;
  }

  public void setUsername(String username) {
    this.username = username;
  }

  public Long getTravelId() {
    return travelId;
  }

  public void setTravelId(Long travelId) {
    this.travelId = travelId;
  }

  public Long getScheduleId() {
    return scheduleId;
  }

  public void setScheduleId(Long scheduleId) {
    this.scheduleId = scheduleId;
  }

  public int getPeople() {
    return people;
  }

  public void setPeople(int people) {
    this.people = people;
  }

  public LocalDateTime getReserveDate() {
    return reserveDate;
  }

  public void setReserveDate(LocalDateTime reserveDate) {
    this.reserveDate = reserveDate;
  }
}
